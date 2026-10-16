from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from e_metaxy.mcp.tools import TOOLS
from e_metaxy.models.task import TaskState

if TYPE_CHECKING:
    from fakes import Connect


async def test_tools_listed_with_hints(connect: Connect) -> None:
    async with connect() as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert sorted(listed) == sorted(TOOLS)
        hints = {name: tool.annotations for name, tool in listed.items()}
        assert (hints["session_read"] and hints["session_read"].read_only_hint) is True
        assert (hints["work_cancel"] and hints["work_cancel"].destructive_hint) is True
        assert listed["work_start"].title == "Start work in Claude Code"


async def test_tools_work_start_lists_the_profiles(connect: Connect) -> None:
    async with connect() as client:
        start = next(tool for tool in (await client.list_tools()).tools if tool.name == "work_start")
        assert "- research (dontAsk): read and search only" in (start.description or "")
        assert "{profiles}" not in (start.description or "")


async def test_tools_work_flow(connect: Connect) -> None:
    async with connect() as client:
        started = await client.call_tool("work_start", {"prompt": "ping", "profile": "research", "project": "/tmp"})
        task = started.structured_content
        assert (started.is_error, task["state"]) == (False, TaskState.RUNNING)
        status = (await client.call_tool("work_status", {"task": task["id"], "wait": 2})).structured_content
        listed = await client.call_tool("work_list", {"limit": 5})
        assert (status["state"], status["result"], [t["id"] for t in listed.structured_content["result"]]) == (
            "done",
            "pong",
            [task["id"]],
        )


async def test_tools_work_cancel_finished(connect: Connect) -> None:
    async with connect() as client:
        task = (
            await client.call_tool("work_start", {"prompt": "p", "profile": "research", "project": "/tmp"})
        ).structured_content
        await client.call_tool("work_status", {"task": task["id"], "wait": 2})
        assert (await client.call_tool("work_cancel", {"task": task["id"]})).structured_content["state"] == "done"


async def test_tools_catalog(connect: Connect) -> None:
    async with connect() as client:
        catalog = (await client.call_tool("catalog", {"project": "/tmp"})).structured_content
        assert ([c["name"] for c in catalog["commands"]], [a["name"] for a in catalog["agents"]]) == (
            ["research"],
            ["architect"],
        )


async def test_tools_session_find_read_update(connect: Connect) -> None:
    async with connect() as client:
        found = (await client.call_tool("session_find", {"text": "voice"})).structured_content["result"]
        read = (await client.call_tool("session_read", {"session": "s-new", "last": 2})).structured_content
        updated = (
            await client.call_tool("session_update", {"session": "s-new", "title": "vad fixed", "tag": "done"})
        ).structured_content
        assert [row["session"] for row in found] == ["s-new"]
        assert [(t["role"], t["text"]) for t in read["turns"]] == [
            ("tool", "Edit"),
            ("assistant", "Threshold lowered to 0.4; tests green."),
        ]
        assert (updated["title"], updated["tag"]) == ("vad fixed", "done")


async def test_tools_live(connect: Connect) -> None:
    async with connect() as client:
        peers = (await client.call_tool("live_list", {})).structured_content["result"]
        receipt = (await client.call_tool("live_send", {"peer": peers[0]["name"], "text": "hola"})).structured_content
        assert ([p["status"] for p in peers], receipt["delivered"]) == (["busy"], True)


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("work_start", {"prompt": "p", "profile": "nope", "project": "/tmp"}, "unknown profile"),
        ("work_start", {"prompt": "p", "profile": "research", "project": "/etc"}, "outside the roots"),
        ("work_start", {"prompt": "p", "profile": "research", "project": "no-such-project"}, "no project named"),
        ("work_status", {"task": "missing"}, "unknown task"),
        ("session_read", {"session": "gone"}, "unknown session"),
        ("session_update", {"session": "gone", "title": "x"}, "unknown session"),
    ],
    ids=["profile", "root", "project", "task", "read", "update"],
)
async def test_tools_refused(connect: Connect, tool: str, arguments: dict, message: str) -> None:
    async with connect() as client:
        result = await client.call_tool(tool, arguments)
        assert result.is_error
        assert message in str(result.content)


async def test_tools_scope_missing_refused(connect: Connect, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("e_metaxy.mcp.tools.get_access_token", lambda: SimpleNamespace(scopes=["sessions"]))
    async with connect() as client:
        refused = await client.call_tool("work_list", {})
        allowed = await client.call_tool("session_find", {})
        assert (refused.is_error, "lacks the 'work' scope" in str(refused.content), allowed.is_error) == (
            True,
            True,
            False,
        )
