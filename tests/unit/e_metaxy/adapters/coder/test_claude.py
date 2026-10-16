from types import SimpleNamespace
from typing import TYPE_CHECKING

import msgspec
import pytest
from claude_agent_sdk import AssistantMessage, CLINotFoundError, ResultError, ResultMessage, SystemMessage
from fakes import INIT, sdk_stream
from mcp.types import CallToolResult, TextContent

from e_metaxy.adapters.coder.claude import CHILD_ENV, TURN_CHARS, ClaudeCoder, Query
from e_metaxy.models.coder import CoderSpec, FinishedEvent, PeerStatus, StartedEvent

if TYPE_CHECKING:
    from collections.abc import Mapping

    from e_metaxy.models.profile import Profile


@pytest.fixture
def claude() -> ClaudeCoder:
    return ClaudeCoder("/usr/bin/claude")


@pytest.fixture
def spec(book: Mapping[str, Profile]) -> CoderSpec:
    return CoderSpec(prompt="p", cwd="/tmp", profile=book["code"], session="s-1", fork=True)


async def test_claude_run_options(claude: ClaudeCoder, spec: CoderSpec) -> None:
    options = claude._run_options(spec)
    assert (
        options.permission_mode,
        options.allowed_tools,
        options.disallowed_tools,
        options.setting_sources,
        options.resume,
        options.fork_session,
        options.max_budget_usd,
        options.cli_path,
        options.env,
    ) == (
        "acceptEdits",
        ["Read", "Grep", "Glob", "Edit", "Write", "Bash"],
        ["Bash(git push*)"],
        ["user", "project"],
        "s-1",
        True,
        2.5,
        "/usr/bin/claude",
        CHILD_ENV,
    )


async def test_claude_run_options_fresh(claude: ClaudeCoder, book: Mapping[str, Profile]) -> None:
    options = claude._run_options(CoderSpec(prompt="p", cwd="/tmp", profile=book["research"]))
    assert (options.resume, options.fork_session, options.max_turns) == (None, False, 8)


async def test_claude_run_options_bypass(claude: ClaudeCoder, book: Mapping[str, Profile]) -> None:
    options = claude._run_options(CoderSpec(prompt="p", cwd="/tmp", profile=book["direct"]))
    assert (
        options.permission_mode,
        options.allowed_tools,
        options.max_turns,
        options.max_budget_usd,
    ) == ("bypassPermissions", [], None, None)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            SystemMessage(subtype="init", data={"session_id": "s-1", "apiKeySource": "none"}),
            StartedEvent(session="s-1"),
        ),
        (
            ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=2,
                session_id="s-1",
                total_cost_usd=0.2,
                result="ok",
            ),
            FinishedEvent(session="s-1", result="ok", cost=0.2, turns=2),
        ),
        (
            ResultMessage(
                subtype="error_max_turns",
                duration_ms=1,
                duration_api_ms=1,
                is_error=True,
                num_turns=8,
                session_id="s-1",
            ),
            FinishedEvent(session="s-1", failed=True, error="error_max_turns", turns=8),
        ),
        (
            ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=True,
                num_turns=1,
                session_id="s-1",
                errors=["API Error: 529"],
            ),
            FinishedEvent(session="s-1", failed=True, error="API Error: 529", turns=1),
        ),
        (SystemMessage(subtype="compact", data={}), None),
        (AssistantMessage(content=[], model="m"), None),
    ],
    ids=["init", "success", "max-turns", "api-error", "other-system", "assistant"],
)
async def test_claude_run_event(message: object, expected: object) -> None:
    assert ClaudeCoder._run_event(message) == expected


async def test_claude_peers_parse() -> None:
    listing = {
        "sections": [
            {
                "kind": "sessions",
                "rows": [
                    {"name": "e-engineer-bc", "ref": "1c9776", "type": "interactive", "status": "busy"},
                    {"name": "e-jev-43", "ref": "2bfe88", "type": "interactive", "status": "asleep"},
                ],
            },
            {"kind": "agents", "rows": [{"name": "sub", "status": "idle"}]},
        ]
    }
    peers = ClaudeCoder._peers_parse(msgspec.json.encode(listing).decode())
    assert [(p.name, p.ref, p.kind, p.status) for p in peers] == [
        ("e-engineer-bc", "1c9776", "interactive", PeerStatus.BUSY),
        ("e-jev-43", "2bfe88", "interactive", PeerStatus.UNKNOWN),
    ]


@pytest.mark.parametrize(
    ("result", "delivered", "detail"),
    [
        (
            CallToolResult(content=[TextContent(type="text", text='{"success":true,"message":"queued"}')]),
            True,
            "queued",
        ),
        (
            CallToolResult(content=[TextContent(type="text", text='{"success":false,"message":"refused"}')]),
            False,
            "refused",
        ),
        (CallToolResult(content=[TextContent(type="text", text="no such peer")], is_error=True), False, "no such peer"),
    ],
    ids=["delivered", "refused", "tool-error"],
)
async def test_claude_send_parse(result: CallToolResult, delivered: bool, detail: str) -> None:
    receipt = ClaudeCoder._send_parse("e-jev-43", result)
    assert (receipt.peer, receipt.delivered, receipt.detail) == ("e-jev-43", delivered, detail)


def row(session: str, modified: int, **fields: object) -> SimpleNamespace:
    base = {"custom_title": None, "summary": "", "first_prompt": None, "cwd": None, "git_branch": None, "tag": None}
    return SimpleNamespace(session_id=session, last_modified=modified, **(base | fields))


async def test_claude_sessions_parse() -> None:
    rows = [
        row("s-a", 1_000, summary="first", cwd="/x", first_prompt="p"),
        row("s-b", 3_000, first_prompt="fallback", git_branch="feat/x", tag="voice"),
        row("s-c", 2_000, custom_title="named", summary="third", cwd="/y"),
    ]
    sessions = ClaudeCoder._sessions_parse(rows, limit=2)
    assert [(s.session, s.title, s.cwd, s.branch, s.tag) for s in sessions] == [
        ("s-b", "fallback", "", "feat/x", "voice"),
        ("s-c", "named", "/y", "", ""),
    ]
    assert sessions[0].modified.timestamp() == 3.0


async def test_claude_sessions_off_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    def listing(*, directory: str | None, limit: int | None, offset: int = 0, include_worktrees: bool = True) -> list:
        return [row("s-1", 1, summary="work", cwd=directory or "")]

    monkeypatch.setattr("e_metaxy.adapters.coder.claude.list_sessions", listing)
    sessions = await ClaudeCoder().sessions("/tmp", 5)
    assert [(s.session, s.cwd) for s in sessions] == [("s-1", "/tmp")]


def message(kind: str, content: object) -> SimpleNamespace:
    return SimpleNamespace(type=kind, message={"role": kind, "content": content})


async def test_claude_turns_parse() -> None:
    messages = [
        message("user", "fix the vad"),
        message("assistant", [{"type": "thinking", "thinking": "hm"}, {"type": "tool_use", "name": "Edit"}]),
        message("user", [{"type": "tool_result", "content": "ok"}]),
        message("assistant", [{"type": "text", "text": "done, tests green"}]),
        SimpleNamespace(type="system", message={"content": "noise"}),
    ]
    turns = ClaudeCoder._turns_parse(messages, last=3)
    assert [(t.role, t.text) for t in turns] == [
        ("user", "fix the vad"),
        ("tool", "Edit"),
        ("assistant", "done, tests green"),
    ]
    assert ClaudeCoder._turns_parse(messages, last=0) == []


async def test_claude_turns_cut_long_text() -> None:
    turns = ClaudeCoder._turns_parse([message("assistant", "x" * 9000)], last=1)
    assert len(turns[0].text) == TURN_CHARS


async def test_claude_catalog_parse() -> None:
    info = {
        "commands": [
            {"name": "research", "description": "survey", "argumentHint": "<topic>"},
            {"description": "nameless"},
        ],
        "agents": [{"name": "architect", "description": "boundaries"}],
    }
    catalog = ClaudeCoder._catalog_parse("/w", info)
    assert [(c.name, c.hint) for c in catalog.commands] == [("research", "<topic>")]
    assert [a.name for a in catalog.agents] == ["architect"]


async def test_claude_session_read_and_update_off_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        "e_metaxy.adapters.coder.claude.get_session_info",
        lambda session, directory=None: row(session, 5, custom_title="t") if session == "s-1" else None,
    )
    monkeypatch.setattr(
        "e_metaxy.adapters.coder.claude.get_session_messages",
        lambda session, directory=None, limit=None, offset=0: [message("assistant", "hi")],
    )
    monkeypatch.setattr(
        "e_metaxy.adapters.coder.claude.rename_session",
        lambda session, title, directory=None: calls.append(("rename", session, title)),
    )
    monkeypatch.setattr(
        "e_metaxy.adapters.coder.claude.tag_session",
        lambda session, tag, directory=None: calls.append(("tag", session, str(tag))),
    )
    coder = ClaudeCoder()
    found, missing = await coder.session("s-1"), await coder.session("s-2")
    assert (found is not None and found.title, missing) == ("t", None)
    assert [t.text for t in await coder.turns("s-1", 5)] == ["hi"]
    await coder.update("s-1", " new name ", "")
    await coder.update("s-1", None, None)
    assert calls == [("rename", "s-1", "new name"), ("tag", "s-1", "None")]


async def test_claude_unconnected(claude: ClaudeCoder) -> None:
    with pytest.raises(RuntimeError, match="not connected"):
        await claude.peers()


async def test_claude_peers_live_child(fake_claude: str) -> None:
    async with ClaudeCoder(fake_claude) as claude:
        peers = await claude.peers()
        delivered = await claude.send("e-jev-43", "hola\nmore")
        refused = await claude.send("ghost", "hola")
    assert ([p.status for p in peers], delivered.delivered, delivered.detail, refused.delivered) == (
        [PeerStatus.BUSY, PeerStatus.IDLE],
        True,
        "hola -> e-jev-43",
        False,
    )


DONE = ResultMessage(
    subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s-1", result="ok"
)
FAILED = ResultMessage(
    subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=8, session_id="s-1"
)


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        (sdk_stream([INIT, AssistantMessage(content=[], model="m"), DONE]), [StartedEvent(session="s-1"), "ok"]),
        (sdk_stream([INIT, FAILED], raises=ResultError("max turns")), [StartedEvent(session="s-1"), "error_max_turns"]),
        (sdk_stream([], raises=CLINotFoundError("no claude")), ["CLINotFoundError"]),
    ],
    ids=["done", "error-result", "sdk-failure"],
)
async def test_claude_run(spec: CoderSpec, stream: Query, expected: list[object]) -> None:
    events = [event async for event in ClaudeCoder("claude", runner=stream).run(spec)]
    seen = [e if isinstance(e, StartedEvent) else (e.result or e.error.split("(")[0]) for e in events]
    assert seen == expected


async def test_claude_catalog_connects_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def __init__(self, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get_server_info(self) -> dict | None:
            return {"commands": [{"name": "review", "description": "d"}], "agents": []}

    monkeypatch.setattr("e_metaxy.adapters.coder.claude.ClaudeSDKClient", Client)
    catalog = await ClaudeCoder().catalog("/w")
    assert (catalog.cwd, [c.name for c in catalog.commands]) == ("/w", ["review"])
