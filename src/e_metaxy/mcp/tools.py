"""e_metaxy.mcp.tools: the bridge as MCP tools — thin, typed, every answer a plain JSON value.

Each method is one tool; the composition root registers them by name. A refusal of the bridge (`MetaxyError`)
surfaces as the tool's error message, which is what an agent can act on."""

from collections.abc import Awaitable
from typing import Any

import msgspec
from beartype import beartype
from mcp.server.mcpserver.exceptions import ToolError

from core.struct import CheckedStruct
from e_metaxy.logic.bridge import Bridge
from e_metaxy.models.error import MetaxyError
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import TaskOrder, TaskState


@beartype
class BridgeTools:
    """The MCP surface over one bridge."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    ##### PRIVATE METHODS #####

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
        self, *, prompt: str, profile: str, cwd: str, session: str = "", fork: bool = False, caller: str = ""
    ) -> dict[str, Any]:
        """Start a coder task and return at once with its id. `profile` fixes what the coder may do (see
        profile_list); `cwd` must lie under the profile's roots; `session` resumes an earlier coder session and
        `fork` branches it instead; `caller` names who to call back when it ends (e.g. "openhuman").
        A skill or slash command is a prompt: "/research vLLM sleep mode"."""
        order = TaskOrder(prompt=prompt, profile=profile, cwd=cwd, session=session, fork=fork, caller=caller)
        return await self._common_plain(self._bridge.start(order))

    async def status(self, task: str, wait: float = 0.0) -> dict[str, Any]:
        """The task: state (running, done, failed, cancelled), session, result, error, cost. `wait` seconds (keep it
        under your client's timeout) returns as soon as the task ends instead of right away."""
        return await self._common_plain(self._bridge.status(task, min(wait, 25.0)))

    async def cancel(self, task: str) -> dict[str, Any]:
        """Interrupt a running task; a finished one comes back unchanged."""
        return await self._common_plain(self._bridge.cancel(task))

    async def tasks(self, state: TaskState | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """The newest tasks, newest first, optionally of one state."""
        return await self._common_plain(self._bridge.tasks(state, limit))

    async def sessions(self, coder: CoderKind = CoderKind.CLAUDE) -> list[dict[str, Any]]:
        """The coder's live interactive sessions: name, ref, kind, idle or busy."""
        return await self._common_plain(self._bridge.peers(coder))

    async def send(self, peer: str, text: str, coder: CoderKind = CoderKind.CLAUDE) -> dict[str, Any]:
        """Deliver `text` to a live session by name (see session_list); it reads it at its next step."""
        return await self._common_plain(self._bridge.send(peer, text, coder))

    async def profiles(self) -> list[dict[str, Any]]:
        """The profiles a task may run under: coder, permission mode, tools, roots, limits."""
        return await self._common_plain(self._bridge.profiles())
