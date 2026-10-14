"""e_metaxy.main: the composition root — the only module that names concretions and wires them to ports.

`assemble` is granian's factory: it reads the settings and the profile book, builds the adapters, the bridge
and the MCP server, and returns the ASGI app whose lifespan opens and closes all of them in order."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Final

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount

from adapters.sqlite import SQLiteAdapter
from core.settings.db import DbSettings
from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.adapters.notifier.openhuman import OpenHumanNotifier
from e_metaxy.config.metaxy import MetaxySettings
from e_metaxy.logic.bridge import Bridge
from e_metaxy.mcp.guard import TokenGuard
from e_metaxy.mcp.tools import BridgeTools
from e_metaxy.models.profile import Profile

INSTRUCTIONS: Final = (
    "e-metaxy carries tasks to engineer harnesses (Claude Code) and their results back. task_start returns at once "
    "with a task id: poll task_status, or pass caller to be called back when it ends. Pick a profile from "
    "profile_list; cwd must lie under its roots. session_list and session_send reach live interactive sessions."
)


def tools(server: MCPServer, surface: BridgeTools) -> MCPServer:
    """Explicit registration: every tool by its public name, nothing bound by a decorator."""
    table: Mapping[str, Callable[..., Any]] = {
        "task_start": surface.start,
        "task_status": surface.status,
        "task_cancel": surface.cancel,
        "task_list": surface.tasks,
        "session_list": surface.sessions,
        "session_send": surface.send,
        "profile_list": surface.profiles,
    }
    _ = [server.add_tool(fn, name=name) for name, fn in table.items()]
    return server


def notifiers(st: MetaxySettings) -> dict[str, OpenHumanNotifier]:
    """The callers the bridge can call back — OpenHuman only when its core token is configured."""
    match st.openhuman_token:
        case None:
            return {}
        case token:
            return {OpenHumanNotifier.name: OpenHumanNotifier(st.openhuman_url, token.get_secret_value())}


def assemble(st: MetaxySettings | None = None) -> Any:
    """The ASGI app: MCP over Streamable HTTP on loopback, the bridge behind it, the bearer gate in front."""
    st = MetaxySettings() if st is None else st
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
    server = tools(MCPServer(name="e-metaxy", instructions=INSTRUCTIONS), BridgeTools(bridge))
    security = TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{st.port}", f"localhost:{st.port}"],
        allowed_origins=[f"http://127.0.0.1:{st.port}", f"http://localhost:{st.port}"],
    )
    mcp_app = server.streamable_http_app(json_response=True, transport_security=security, host=st.host)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            _ = [await stack.enter_async_context(edge) for edge in (ledger, claude, *callers.values())]
            await stack.enter_async_context(bridge)
            await stack.enter_async_context(server.session_manager.run())
            yield

    app = Starlette(routes=[Mount("/", app=mcp_app)], lifespan=lifespan)
    match st.token:
        case None:
            return app
        case token:
            return TokenGuard(app, token.get_secret_value())
