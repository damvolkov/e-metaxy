"""e_metaxy.adapters.coder.claude: Claude Code as a coder — the Agent SDK runs, a `claude mcp serve` child reaches peers.

A run is one Agent SDK query on the profile's policy, with the user's `~/.claude` loaded (CLAUDE.md, skills,
agents, hooks) and the subscription login inherited: an API key in the environment is blanked for the child.
Live interactive sessions are reached through the CLI's own MCP server — its ListAgents and SendMessage tools —
held open for the adapter's lifetime."""

from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from functools import partial
from typing import Any, ClassVar, Final

import anyio
import msgspec
import structlog
from beartype import beartype
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultError,
    ResultMessage,
    SystemMessage,
    list_sessions,
    query,
)
from claude_agent_sdk.types import SettingSource
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult, TextContent

from e_metaxy.adapters.base import BaseAdapter
from e_metaxy.models.coder import (
    CoderEvent,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    PeerStatus,
    StartedEvent,
)
from e_metaxy.models.profile import CoderKind

log = structlog.get_logger()

type Query = Callable[..., AsyncIterator[object]]

SOURCES: Final[tuple[SettingSource, ...]] = ("user", "project")
### the subscription login, never a key that happens to sit in the service's environment.
CHILD_ENV: Final = {"ANTHROPIC_API_KEY": ""}


@beartype
class ClaudeCoder(BaseAdapter):
    """Runs specs on the Agent SDK; lists and messages the host's live Claude Code sessions."""

    name: ClassVar[str] = "claude"
    kind: ClassVar[CoderKind] = CoderKind.CLAUDE

    __slots__ = ("_cli", "_client", "_query", "_stack")

    def __init__(self, cli: str = "claude", runner: Query = query) -> None:
        self._cli = cli
        self._query = runner
        self._stack = AsyncExitStack()
        self._client: Client | None = None

    ##### PRIVATE METHODS #####

    def _run_options(self, spec: CoderSpec) -> ClaudeAgentOptions:
        profile = spec.profile
        return ClaudeAgentOptions(
            cwd=spec.cwd,
            permission_mode=profile.mode.value,
            allowed_tools=list(profile.allow),
            disallowed_tools=list(profile.deny),
            setting_sources=list(SOURCES),
            max_turns=profile.turns,
            max_budget_usd=profile.budget,
            model=profile.model,
            resume=spec.session or None,
            fork_session=spec.fork,
            cli_path=self._cli,
            env=dict(CHILD_ENV),
        )

    @staticmethod
    def _run_event(message: object) -> CoderEvent | None:
        """The SDK message as a bridge event: the init frame starts, the result frame finishes, the rest is noise."""
        match message:
            case SystemMessage(subtype="init", data={"session_id": str(session), **rest}):
                log.info(
                    "CLAUDE_SESSION", session=session, key=rest.get("apiKeySource", ""), model=rest.get("model", "")
                )
                return StartedEvent(session=session)
            case ResultMessage() as result:
                return FinishedEvent(
                    session=result.session_id,
                    result=result.result or "",
                    failed=result.is_error,
                    error="; ".join(result.errors or ()) or (result.subtype if result.is_error else ""),
                    cost=result.total_cost_usd or 0.0,
                    turns=result.num_turns,
                )
            case _:
                return None

    def _common_client(self) -> Client:
        match self._client:
            case None:
                msg = "ClaudeCoder not connected: the lifespan opens it, tools never do"
                raise RuntimeError(msg)
            case client:
                return client

    @staticmethod
    def _common_text(result: CallToolResult) -> str:
        return "".join(block.text for block in result.content if isinstance(block, TextContent))

    @staticmethod
    def _peers_parse(text: str) -> list[CoderPeer]:
        """ListAgents' JSON listing → the session rows as peers."""
        listing: dict[str, Any] = msgspec.json.decode(text)
        rows = [
            row
            for section in listing.get("sections", ())
            if section.get("kind") == "sessions"
            for row in section["rows"]
        ]
        return [
            CoderPeer(
                name=row["name"],
                ref=row.get("ref", ""),
                kind=row.get("type", ""),
                status=PeerStatus(row["status"]) if row.get("status") in PeerStatus else PeerStatus.UNKNOWN,
            )
            for row in rows
        ]

    @classmethod
    def _send_parse(cls, peer: str, result: CallToolResult) -> CoderReceipt:
        """SendMessage's verdict: a tool error or `success: false` is undelivered, its reason kept."""
        text = cls._common_text(result)
        verdict: dict[str, Any] = {"success": False, "message": text} if result.is_error else msgspec.json.decode(text)
        return CoderReceipt(peer=peer, delivered=bool(verdict.get("success")), detail=verdict.get("message", ""))

    @staticmethod
    def _history_parse(rows: list[Any], limit: int) -> list[CoderSession]:
        """The SDK's session rows, newest first, trimmed to the limit."""
        ordered = sorted(rows, key=lambda row: row.last_modified, reverse=True)[:limit]
        return [
            CoderSession(
                session=row.session_id,
                title=row.summary or row.first_prompt or "",
                cwd=row.cwd or "",
                modified=datetime.fromtimestamp(row.last_modified / 1000, tz=UTC),
            )
            for row in ordered
        ]

    ############################################################

    ##### LIFECYCLE #####

    async def connect(self) -> None:
        params = StdioServerParameters(command=self._cli, args=["mcp", "serve"])
        self._client = await self._stack.enter_async_context(Client(params))

    async def close(self) -> None:
        await self._stack.aclose()
        self._client = None

    ##### PUBLIC #####

    async def run(self, spec: CoderSpec) -> AsyncIterator[CoderEvent]:
        """The run's events; an SDK failure becomes a failed finish, a cancellation closes the CLI process."""
        try:
            async for event in (
                e
                async for m in self._query(prompt=spec.prompt, options=self._run_options(spec))
                if (e := self._run_event(m))
            ):
                yield event
        except ResultError:
            ### the CLI raised after emitting its error result, which already left as a FinishedEvent.
            return
        except ClaudeSDKError as exc:
            yield FinishedEvent(failed=True, error=repr(exc))

    async def peers(self) -> list[CoderPeer]:
        return self._peers_parse(self._common_text(await self._common_client().call_tool("ListAgents", {})))

    async def send(self, peer: str, text: str) -> CoderReceipt:
        arguments = {"to": peer, "message": text, "summary": text.splitlines()[0][:80] if text else "e-metaxy"}
        return self._send_parse(peer, await self._common_client().call_tool("SendMessage", arguments))

    async def history(self, cwd: str, limit: int) -> list[CoderSession]:
        """Recorded sessions on disk: a head/tail read off the loop, no CLI process involved."""
        rows = await anyio.to_thread.run_sync(partial(list_sessions, directory=cwd or None, limit=None))
        return self._history_parse(rows, limit)
