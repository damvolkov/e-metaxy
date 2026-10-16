"""e_metaxy.main: the composition root — the only module that names concretions and wires them to ports.

`assemble` is granian's factory: it reads the settings and the profile book, builds the crypto engine once and
hands it to the authority, builds the adapters, the bridge and the MCP server, and returns the ASGI app whose
lifespan opens and closes all of them in order. Every door but the consent page asks for a bearer token the
authority issued: the MCP endpoint through the SDK, the REST converters through the same verifier."""

import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Final

import structlog
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount

from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.adapters.md.anytomd import AnytomdAdapter
from e_metaxy.adapters.notifier.openhuman import OpenHumanNotifier
from e_metaxy.adapters.owner.passphrase import PassphraseOwner
from e_metaxy.adapters.sqlite import SQLiteAdapter
from e_metaxy.api.consent import ConsentApi
from e_metaxy.api.converters import create_app
from e_metaxy.config.authority import AuthoritySettings
from e_metaxy.config.metaxy import MetaxySettings
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.logger import setup
from e_metaxy.core.settings import settings as core
from e_metaxy.core.settings.db import DbSettings
from e_metaxy.logic.authority import Authority
from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.converters import Converters
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.mcp.converters import ProcessorTools
from e_metaxy.mcp.tools import BridgeTools, register
from e_metaxy.models.auth import Scope
from e_metaxy.models.error import OwnerUnsetError
from e_metaxy.models.profile import Profile
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor

INSTRUCTIONS: Final = (
    "e-metaxy drives Claude Code on this machine with the user's own setup (CLAUDE.md, skills, commands, agents, "
    "hooks). Work runs in the background: work_start returns at once with a task id and its session; work_status "
    "watches it; caller='openhuman' calls you back when it ends. A session is a Claude Code conversation: "
    "session_find locates one, session_read shows where it stopped, work_start with session=<id> continues it. "
    "catalog lists the commands and skills a project offers. A project is a short name ('e-voice') or a path."
)


class _ToStructlog(logging.Handler):
    """A stdlib record as a structlog event: what the MCP SDK logs through rich enters the house renderer."""

    def emit(self, record: logging.LogRecord) -> None:
        structlog.get_logger(record.name).log(
            record.levelno, record.getMessage(), exc_info=record.exc_info, stack_info=record.stack_info
        )


def quiet() -> None:
    """Route the third-party stdlib logs to structlog — before any MCPServer is built, so the SDK's
    `basicConfig` finds the root already handled and installs no RichHandler of its own."""
    if not any(isinstance(handler, _ToStructlog) for handler in logging.root.handlers):
        logging.root.addHandler(_ToStructlog())
    logging.root.setLevel(logging.INFO)


def notifiers(st: MetaxySettings) -> dict[str, OpenHumanNotifier]:
    """The callers the bridge can call back — OpenHuman only when its core token is configured."""
    match st.openhuman_token:
        case None:
            return {}
        case token:
            return {
                OpenHumanNotifier.name: OpenHumanNotifier(
                    st.openhuman_url, token.get_secret_value(), timeout=st.openhuman_timeout
                )
            }


def owner(crypto: Crypto, auth: AuthoritySettings) -> PassphraseOwner:
    """The owner who approves clients; the bridge refuses to start without one."""
    match auth.owner_hash:
        case None:
            raise OwnerUnsetError
        case hashed:
            return PassphraseOwner(crypto, hashed.get_secret_value())


def auth_settings(auth: AuthoritySettings) -> AuthSettings:
    """The SDK's view of the authority: issuer, the protected MCP resource, open registration, revocation.

    Built from strings: the SDK keeps a path-less issuer canonical only then (no trailing slash), and RFC 8414
    compares issuers byte for byte — the issuer in the metadata must be the `iss` the tokens carry."""
    scopes = [scope.value for scope in Scope]
    return AuthSettings.model_validate(
        {
            "issuer_url": auth.issuer,
            "resource_server_url": auth.resource,
            "validate_token_resource": True,
            "client_registration_options": {"enabled": True, "valid_scopes": scopes, "default_scopes": scopes},
            "revocation_options": {"enabled": True},
        }
    )


def assemble(
    st: MetaxySettings | None = None, auth: AuthoritySettings | None = None, crypto: Crypto | None = None
) -> Any:
    """The ASGI app: MCP over Streamable HTTP on loopback, the bridge behind it, the authority in front."""
    st = MetaxySettings() if st is None else st
    auth = AuthoritySettings() if auth is None else auth
    ### granian imports the factory in its worker process: the logger is configured where the app runs.
    setup(env=core.app.app_env)
    quiet()
    crypto = Crypto(core.crypto) if crypto is None else crypto
    ledger = SQLiteAdapter(DbSettings(db_path=st.ledger.expanduser()))
    authority = Authority(crypto=crypto, store=ledger, owner=owner(crypto, auth), policy=auth.policy)
    claude = ClaudeCoder(st.claude)
    callers = notifiers(st)
    profiles = Profile.book(st.profiles.expanduser().read_bytes())
    bridge = Bridge(
        coders={claude.kind: claude},
        notifiers=callers,
        ledger=ledger,
        profiles=profiles,
        projects=ProjectIndex(st.workspaces),
        limit=st.limit,
    )
    ### the processors over their ports: the fast any-format renderer and the deep document reader.
    anatomd, docling = AnytomdAdapter(), DoclingAdapter()
    converters = Converters(MDProcessor(anatomd), DocProcessor(docling))
    processors = ProcessorTools(converters)
    server = register(
        MCPServer(name="e-metaxy", instructions=INSTRUCTIONS, auth_server_provider=authority, auth=auth_settings(auth)),
        BridgeTools(bridge),
        profiles,
    )
    server.add_tool(processors.convert, name="md_convert")
    server.add_tool(processors.read, name="doc_read")
    security = TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{st.port}", f"localhost:{st.port}"],
        allowed_origins=[f"http://127.0.0.1:{st.port}", f"http://localhost:{st.port}"],
    )
    mcp_app = server.streamable_http_app(json_response=True, transport_security=security, host=st.host)
    ops = RequireAuthMiddleware(
        create_app(converters), [Scope.WORK.value], build_resource_metadata_url(AnyHttpUrl(auth.resource))
    )
    gate = [
        Middleware(
            AuthenticationMiddleware,
            backend=BearerAuthBackend(ProviderTokenVerifier(authority), resource_server_url=AnyHttpUrl(auth.resource)),
        ),
        Middleware(AuthContextMiddleware),
    ]

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            _ = [
                await stack.enter_async_context(edge) for edge in (ledger, claude, anatomd, docling, *callers.values())
            ]
            await stack.enter_async_context(bridge)
            await stack.enter_async_context(server.session_manager.run())
            yield

    return Starlette(
        routes=[*ConsentApi(authority).routes(), Mount("/ops", app=ops), Mount("/", app=mcp_app)],
        middleware=gate,
        lifespan=lifespan,
    )
