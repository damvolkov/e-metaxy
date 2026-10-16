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
    ClaudeSDKClient,
    ClaudeSDKError,
    ResultError,
    ResultMessage,
    SystemMessage,
    get_session_info,
    get_session_messages,
    list_sessions,
    query,
    rename_session,
    tag_session,
)
from claude_agent_sdk.types import SettingSource
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult, TextContent

from e_metaxy.adapters.base import BaseAdapter
from e_metaxy.models.coder import (
    CatalogEntry,
    CoderCatalog,
    CoderEvent,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    PeerStatus,
    SessionTurn,
    StartedEvent,
    TurnRole,
)
from e_metaxy.models.profile import CoderKind

log = structlog.get_logger()

type Query = Callable[..., AsyncIterator[object]]

SOURCES: Final[tuple[SettingSource, ...]] = ("user", "project")
### the subscription login, never a key that happens to sit in the service's environment.
CHILD_ENV: Final = {"ANTHROPIC_API_KEY": ""}
### a turn longer than this is cut: the read is a summary to pick a session up, not a transcript export.
TURN_CHARS: Final = 4000


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
    def _common_session(row: Any) -> CoderSession:
        """The SDK's session row as a session: its own title first, then the SDK's summary, then the first ask."""
        return CoderSession(
            session=row.session_id,
            title=row.custom_title or row.summary or row.first_prompt or "",
            cwd=row.cwd or "",
            branch=row.git_branch or "",
            tag=row.tag or "",
            modified=datetime.fromtimestamp(row.last_modified / 1000, tz=UTC),
        )

    @classmethod
    def _sessions_parse(cls, rows: list[Any], limit: int) -> list[CoderSession]:
        """The SDK's session rows, newest first, trimmed to the limit."""
        return [
            cls._common_session(row) for row in sorted(rows, key=lambda row: row.last_modified, reverse=True)[:limit]
        ]

    @staticmethod
    def _turns_block(role: str, block: Any) -> SessionTurn | None:
        """One content block as a readable turn: text speaks, a tool call is named, results and thinking stay out."""
        match (role, block):
            case (_, str() as text) if text.strip():
                return SessionTurn(role=TurnRole(role), text=text[:TURN_CHARS])
            case (_, {"type": "text", "text": str(text)}) if text.strip():
                return SessionTurn(role=TurnRole(role), text=text[:TURN_CHARS])
            case ("assistant", {"type": "tool_use", "name": str(name)}):
                return SessionTurn(role=TurnRole.TOOL, text=name)
            case _:
                return None

    @classmethod
    def _turns_parse(cls, messages: list[Any], last: int) -> list[SessionTurn]:
        """The transcript's readable turns, the last `last` of them, oldest first."""
        blocks = (
            (message.type, block)
            for message in messages
            if message.type in {"user", "assistant"} and isinstance(message.message, dict)
            for content in (message.message.get("content"),)
            for block in (content if isinstance(content, list) else [content])
        )
        turns = [turn for role, block in blocks if (turn := cls._turns_block(role, block))]
        return turns[-last:] if last > 0 else []

    @staticmethod
    def _catalog_entries(rows: list[dict[str, Any]]) -> tuple[CatalogEntry, ...]:
        return tuple(
            CatalogEntry(name=row["name"], description=row.get("description", ""), hint=row.get("argumentHint", ""))
            for row in rows
            if row.get("name")
        )

    @classmethod
    def _catalog_parse(cls, cwd: str, info: dict[str, Any]) -> CoderCatalog:
        return CoderCatalog(
            cwd=cwd,
            commands=cls._catalog_entries(info.get("commands", [])),
            agents=cls._catalog_entries(info.get("agents", [])),
        )

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

    async def sessions(self, cwd: str, limit: int) -> list[CoderSession]:
        """Recorded sessions on disk: a head/tail read off the loop, no CLI process involved."""
        rows = await anyio.to_thread.run_sync(partial(list_sessions, directory=cwd or None, limit=None))
        return self._sessions_parse(rows, limit)

    async def session(self, session: str) -> CoderSession | None:
        row = await anyio.to_thread.run_sync(partial(get_session_info, session))
        return None if row is None else self._common_session(row)

    async def turns(self, session: str, last: int) -> list[SessionTurn]:
        messages = await anyio.to_thread.run_sync(partial(get_session_messages, session))
        return self._turns_parse(messages, last)

    async def update(self, session: str, title: str | None, tag: str | None) -> None:
        match title:
            case str() if title.strip():
                await anyio.to_thread.run_sync(partial(rename_session, session, title.strip()))
        match tag:
            case str():
                await anyio.to_thread.run_sync(partial(tag_session, session, tag.strip() or None))

    async def catalog(self, cwd: str) -> CoderCatalog:
        """The CLI's initialize answer, read by connecting and closing — no prompt, no model turn, no cost."""
        options = ClaudeAgentOptions(cwd=cwd, setting_sources=list(SOURCES), cli_path=self._cli, env=dict(CHILD_ENV))
        async with ClaudeSDKClient(options=options) as client:
            info = await client.get_server_info() or {}
        return self._catalog_parse(cwd, info)
