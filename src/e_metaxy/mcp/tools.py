"""e_metaxy.mcp.tools: the bridge as ten MCP tools — what an agent needs to drive Claude Code, nothing more.

Work runs in the background: `work_start` answers at once with the task and its session, `work_status` watches
it, `work_list` shows what is running, `work_cancel` stops it. A session is Claude Code's conversation, the same
one `claude --resume` opens: `session_find` locates it, `session_read` shows where it stopped, `session_update`
names it, and `work_start` with its id continues it. `catalog` says which commands, skills and agents a project
offers; `live_list` / `live_send` reach the sessions open in a terminal.

Every tool checks the scope its token carries; every answer is plain JSON; a refusal of the bridge is the tool's
error message, written so the agent can act on it. Registration is explicit: `TOOLS` is the whole surface."""

from collections.abc import Awaitable, Mapping
from types import MappingProxyType
from typing import Any, Final

import msgspec
from beartype import beartype
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from e_metaxy.core.struct import CheckedStruct
from e_metaxy.logic.bridge import Bridge
from e_metaxy.models.auth import Scope
from e_metaxy.models.error import MetaxyError
from e_metaxy.models.profile import Profile
from e_metaxy.models.task import TaskOrder, TaskState

### an MCP client times out long before a coder finishes: a status wait is capped well under that.
WAIT_CAP: Final = 25.0


class ToolSpec(CheckedStruct, frozen=True, kw_only=True):
    """One tool: the surface method it calls, the scope it needs, and how an agent should read it."""

    method: str
    scope: Scope
    title: str
    description: str
    read_only: bool = False
    destructive: bool = False


TOOLS: Final[Mapping[str, ToolSpec]] = MappingProxyType(
    {
        "work_start": ToolSpec(
            method="start",
            scope=Scope.WORK,
            title="Start work in Claude Code",
            description=(
                "Run a prompt in Claude Code on this machine, with the user's whole setup (CLAUDE.md, skills, "
                "commands, agents, hooks). Returns at once with `id` (the task) and, once known, `session`. "
                '`prompt`: plain words, or a command/skill such as "/research vLLM sleep mode" (see catalog). '
                '`project`: a short name ("e-voice") or a path. `session`: continue that conversation instead of '
                'starting one (its id, the first 8 characters of it, or its exact title); `fork`: branch it. `caller`: who to call back when it ends ("openhuman"). '
                "Next: work_status with `id`; keep `session` to continue later.\n\nProfiles:\n{profiles}"
            ),
        ),
        "work_status": ToolSpec(
            method="status",
            scope=Scope.WORK,
            title="Check a task",
            description=(
                "A task's state (running, done, failed, cancelled), its session, final `result`, `error`, cost and "
                "turns. `wait` (seconds, at most 25) returns as soon as it ends instead of right away."
            ),
            read_only=True,
        ),
        "work_list": ToolSpec(
            method="tasks",
            scope=Scope.WORK,
            title="List tasks",
            description="The newest tasks first — what is running, what finished; `state` narrows to one state.",
            read_only=True,
        ),
        "work_cancel": ToolSpec(
            method="cancel",
            scope=Scope.WORK,
            title="Cancel a task",
            description="Interrupt a running task; a finished one comes back unchanged. Its session can be continued.",
            destructive=True,
        ),
        "catalog": ToolSpec(
            method="catalog",
            scope=Scope.WORK,
            title="What Claude Code offers in a project",
            description=(
                "The slash commands, skills and agents Claude Code has in `project` (short name or path; empty means "
                'the workspace root). Use a command or skill as a work_start prompt: "/<name> <arguments>".'
            ),
            read_only=True,
        ),
        "session_find": ToolSpec(
            method="find",
            scope=Scope.SESSIONS,
            title="Find Claude Code sessions",
            description=(
                "Recorded sessions, newest first: id, title, project, branch, tag, last change. `project` narrows to "
                "one project (short name or path), `text` to titles, branches or tags that contain it. "
                "Next: session_read to see where one stopped, work_start with `session` to continue it."
            ),
            read_only=True,
        ),
        "session_read": ToolSpec(
            method="read",
            scope=Scope.SESSIONS,
            title="Read where a session stopped",
            description=(
                "A session and its last `last` turns, oldest first: what the user asked, what Claude Code answered, "
                "which tools it called. `session`: its id, the first 8 characters of it, or its exact title. "
                "Read it before continuing a session with work_start."
            ),
            read_only=True,
        ),
        "session_update": ToolSpec(
            method="update",
            scope=Scope.SESSIONS,
            title="Rename or tag a session",
            description="Give a session a `title` and/or a `tag` (an empty tag clears it); returns the session.",
        ),
        "live_list": ToolSpec(
            method="peers",
            scope=Scope.LIVE,
            title="List open Claude Code sessions",
            description="The sessions open in a terminal right now: name, kind, idle or busy. live_send reaches one.",
            read_only=True,
        ),
        "live_send": ToolSpec(
            method="send",
            scope=Scope.LIVE,
            title="Message an open session",
            description=(
                "Deliver `text` to an open session by its name (see live_list); it reads it at its next step. "
                "Returns whether it was delivered, not what the session answers."
            ),
        ),
    }
)


@beartype
class BridgeTools:
    """The MCP surface over one bridge."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    ##### PRIVATE METHODS #####

    @staticmethod
    def _common_scope(scope: Scope) -> None:
        """The request's token must carry `scope`; an unauthenticated server (tests, in-memory) has no token."""
        match get_access_token():
            case None:
                return
            case token if scope.value not in token.scopes:
                message = f"this token lacks the {scope.value!r} scope; sign in again granting it"
                raise ToolError(message)

    @staticmethod
    async def _common_plain(call: Awaitable[object]) -> Any:
        """The bridge's answer as JSON builtins; a refusal of the bridge becomes the tool's error message."""
        try:
            value = await call
        except MetaxyError as exc:
            raise ToolError(exc.message) from exc
        return msgspec.to_builtins(value, enc_hook=CheckedStruct.enc_hook)

    ############################################################

    ##### PUBLIC #####

    async def start(
        self,
        *,
        prompt: str,
        project: str,
        profile: str = "code",
        session: str = "",
        fork: bool = False,
        caller: str = "",
    ) -> dict[str, Any]:
        self._common_scope(Scope.WORK)
        order = TaskOrder(prompt=prompt, profile=profile, cwd=project, session=session, fork=fork, caller=caller)
        return await self._common_plain(self._bridge.start(order))

    async def status(self, task: str, wait: float = 0.0) -> dict[str, Any]:
        self._common_scope(Scope.WORK)
        return await self._common_plain(self._bridge.status(task, min(max(wait, 0.0), WAIT_CAP)))

    async def tasks(self, state: TaskState | None = None, limit: int = 20) -> list[dict[str, Any]]:
        self._common_scope(Scope.WORK)
        return await self._common_plain(self._bridge.tasks(state, limit))

    async def cancel(self, task: str) -> dict[str, Any]:
        self._common_scope(Scope.WORK)
        return await self._common_plain(self._bridge.cancel(task))

    async def catalog(self, project: str = "") -> dict[str, Any]:
        self._common_scope(Scope.WORK)
        return await self._common_plain(self._bridge.catalog(project))

    async def find(self, project: str = "", text: str = "", limit: int = 10) -> list[dict[str, Any]]:
        self._common_scope(Scope.SESSIONS)
        return await self._common_plain(self._bridge.find(project, text, limit))

    async def read(self, session: str, last: int = 6) -> dict[str, Any]:
        self._common_scope(Scope.SESSIONS)
        return await self._common_plain(self._bridge.read(session, last))

    async def update(self, session: str, title: str | None = None, tag: str | None = None) -> dict[str, Any]:
        self._common_scope(Scope.SESSIONS)
        return await self._common_plain(self._bridge.update(session, title, tag))

    async def peers(self) -> list[dict[str, Any]]:
        self._common_scope(Scope.LIVE)
        return await self._common_plain(self._bridge.peers())

    async def send(self, peer: str, text: str) -> dict[str, Any]:
        self._common_scope(Scope.LIVE)
        return await self._common_plain(self._bridge.send(peer, text))


def profiles_text(profiles: Mapping[str, Profile]) -> str:
    """The profile book as lines an agent reads in work_start's description: name, mode, note."""
    return "\n".join(f"- {name} ({profile.mode.value}): {profile.note}" for name, profile in profiles.items())


def register(server: Any, surface: BridgeTools, profiles: Mapping[str, Profile]) -> Any:
    """Every tool of `TOOLS` on `server`, explicitly, with its title, description and hints."""
    _ = [
        server.add_tool(
            getattr(surface, spec.method),
            name=name,
            title=spec.title,
            description=spec.description.format(profiles=profiles_text(profiles)),
            annotations=ToolAnnotations(
                read_only_hint=spec.read_only, destructive_hint=spec.destructive, open_world_hint=False
            ),
        )
        for name, spec in TOOLS.items()
    ]
    return server
