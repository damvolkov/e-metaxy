"""core.lifespan.mcp: the MCP server built over the shared services, its session manager run for the app's life.

The server is the authority's protocol face — metadata, dynamic registration, /authorize, /token, /revoke and
the bearer gate on /mcp — and the tools are the bridge's and the converters'. It is built here, after the
services exist, and its Streamable HTTP app lands under `system.mcp`, where the mount forwards to it."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from litestar import Litestar
from litestar.types import ASGIApp
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings

from e_metaxy.core.lifespan.services import ServicesState
from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.logger import logger
from e_metaxy.core.settings import settings as st
from e_metaxy.core.settings.metaxy import MetaxySettings
from e_metaxy.mcp.tools import TOOLS, BridgeTools, ConverterTools, Surface, register
from e_metaxy.models.auth import Policy, Scope

INSTRUCTIONS: Final = (
    "e-metaxy drives Claude Code on this machine with the user's own setup (CLAUDE.md, skills, commands, agents, "
    "hooks). Work runs in the background: work_start returns at once with a task id and its session; work_status "
    "watches it; caller='openhuman' calls you back when it ends. A session is a Claude Code conversation: "
    "session_find locates one, session_read shows where it stopped, work_start with session=<id> continues it. "
    "catalog lists the commands and skills a project offers. A project is a short name ('e-voice') or a path. "
    "A message the user starts with `eng` goes to the eng tool untouched: it parses the shared grammar itself. "
    "md_convert renders any file to Markdown; doc_read reads a document deeply."
)


##### SECTION #####
@dataclass(frozen=True, slots=True)
class McpState:
    """The typed MCP section: the server and the Streamable HTTP app the mount forwards to."""

    server: MCPServer
    app: ASGIApp


def auth(rules: Policy) -> AuthSettings:
    """The SDK's view of the authority: issuer, the protected MCP resource, open registration, revocation.

    Built from strings: the SDK keeps a path-less issuer canonical only then (no trailing slash), and RFC 8414
    compares issuers byte for byte — the issuer in the metadata must be the `iss` the tokens carry."""
    scopes = [scope.value for scope in Scope]
    return AuthSettings.model_validate(
        {
            "issuer_url": rules.issuer,
            "resource_server_url": rules.resource,
            "validate_token_resource": True,
            "client_registration_options": {"enabled": True, "valid_scopes": scopes, "default_scopes": scopes},
            "revocation_options": {"enabled": True},
        }
    )


def security(conf: MetaxySettings) -> TransportSecuritySettings:
    """Loopback only: the Host and Origin a request may carry are this port's, by address or by name."""
    return TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{conf.port}", f"localhost:{conf.port}"],
        allowed_origins=[f"http://127.0.0.1:{conf.port}", f"http://localhost:{conf.port}"],
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Build the server over the services, run its session manager, then mount the section under `system.mcp`."""
    system, conf = AppState.of(app).system, st.metaxy
    services: ServicesState = system.services
    surfaces = {
        Surface.BRIDGE: BridgeTools(services.bridge, services.desk),
        Surface.CONVERTER: ConverterTools(services.converters),
    }
    server = register(
        MCPServer(
            name="e-metaxy",
            instructions=INSTRUCTIONS,
            auth_server_provider=services.authority,
            auth=auth(services.policy),
        ),
        surfaces,
        services.profiles,
    )
    asgi = server.streamable_http_app(json_response=True, transport_security=security(conf), host=conf.host)
    async with server.session_manager.run():
        system.mcp = McpState(server=server, app=asgi)
        logger.info("mcp ready", tools=len(TOOLS), step="START")
        yield
