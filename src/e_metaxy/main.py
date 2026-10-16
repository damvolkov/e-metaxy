"""e_metaxy.main: the composition root — the only module that names concretions and wires them to ports.

`assemble` is granian's factory: it reads the settings and the profile book, builds the adapters, the bridge
and the MCP server, and returns the ASGI app whose lifespan opens and closes all of them in order."""

import logging
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Final

import structlog
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount

from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.adapters.md.anytomd import AnytomdAdapter
from e_metaxy.adapters.notifier.openhuman import OpenHumanNotifier
from e_metaxy.adapters.sqlite import SQLiteAdapter
from e_metaxy.api.converters import create_app
from e_metaxy.config.metaxy import MetaxySettings
from e_metaxy.core.logger import setup
from e_metaxy.core.settings import settings as core
from e_metaxy.core.settings.db import DbSettings
from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.converters import Converters
from e_metaxy.mcp.converters import ProcessorTools
from e_metaxy.mcp.guard import TokenGuard
from e_metaxy.mcp.tools import BridgeTools
from e_metaxy.models.profile import Profile
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor

INSTRUCTIONS: Final = (
    "e-metaxy carries tasks to engineer harnesses (Claude Code) and their results back. task_start returns at once "
    "with a task id: poll task_status, or pass caller to be called back when it ends. Pick a profile from "
    "profile_list; cwd must lie under its roots. session_list shows live interactive sessions, session_history the "
    "recorded ones a task can resume; session_send reaches a live session."
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


def tools(server: MCPServer, surface: BridgeTools, processors: ProcessorTools | None = None) -> MCPServer:
    """Explicit registration: every tool by its public name, nothing bound by a decorator."""
    table: Mapping[str, Callable[..., Any]] = {
        "task_start": surface.start,
        "task_status": surface.status,
        "task_cancel": surface.cancel,
        "task_list": surface.tasks,
        "session_list": surface.sessions,
        "session_history": surface.history,
        "session_send": surface.send,
        "profile_list": surface.profiles,
    } | ({} if processors is None else {"md_convert": processors.convert, "doc_read": processors.read})
    _ = [server.add_tool(fn, name=name) for name, fn in table.items()]
    return server


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


def assemble(st: MetaxySettings | None = None) -> Any:
    """The ASGI app: MCP over Streamable HTTP on loopback, the bridge behind it, the bearer gate in front."""
    st = MetaxySettings() if st is None else st
    ### granian imports the factory in its worker process: the logger is configured where the app runs.
    setup(env=core.app.app_env)
    quiet()
    ledger = SQLiteAdapter(DbSettings(db_path=st.ledger.expanduser()))
    claude = ClaudeCoder(st.claude)
    callers = notifiers(st)
    bridge = Bridge(
        coders={claude.kind: claude},
        notifiers=callers,
        ledger=ledger,
        profiles=Profile.book(st.profiles.expanduser().read_bytes()),
        limit=st.limit,
    )
    ### the processors over their ports: the fast any-format renderer and the deep document reader.
    anatomd, docling = AnytomdAdapter(), DoclingAdapter()
    converters = Converters(MDProcessor(anatomd), DocProcessor(docling))
    server = tools(
        MCPServer(name="e-metaxy", instructions=INSTRUCTIONS),
        BridgeTools(bridge),
        ProcessorTools(converters),
    )
    security = TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{st.port}", f"localhost:{st.port}"],
        allowed_origins=[f"http://127.0.0.1:{st.port}", f"http://localhost:{st.port}"],
    )
    mcp_app = server.streamable_http_app(json_response=True, transport_security=security, host=st.host)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            _ = [
                await stack.enter_async_context(edge) for edge in (ledger, claude, anatomd, docling, *callers.values())
            ]
            await stack.enter_async_context(bridge)
            await stack.enter_async_context(server.session_manager.run())
            yield

    app = Starlette(routes=[Mount("/ops", app=create_app(converters)), Mount("/", app=mcp_app)], lifespan=lifespan)
    match st.token:
        case None:
            return app
        case token:
            return TokenGuard(app, token.get_secret_value())
