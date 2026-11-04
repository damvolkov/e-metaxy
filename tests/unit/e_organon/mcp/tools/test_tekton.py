"""tests/unit/e_organon/mcp/tools/tekton: the tekton tools as an agent meets them — over the MCP endpoint under both
handshakes, a key at every call, the sessions and peers reached, its refusals the tool's error."""

from typing import TYPE_CHECKING

import pytest

from support.mcp import MODES, call, refused

if TYPE_CHECKING:
    from support.mcp import Connect

TASK = {"prompt": "ping", "project": "/tmp", "profile": "research"}


@pytest.mark.parametrize("mode", MODES)
async def test_tekton_tasks_under_both_handshakes(connect: Connect, ana_key: dict[str, str], mode: str) -> None:
    ### no run is started here: the in-process client serves the lifespans on a loop of its own, and the bridge's runs
    ### live on the loop that entered it. The work flow is held by `api/router/tekton`, on the app's own loop.
    listed = await call(connect, "tekton_tasks", {"limit": 5}, ana_key, mode)
    assert isinstance(listed["tasks"], list)


async def test_tekton_sessions_and_peers(connect: Connect, ana_key: dict[str, str]) -> None:
    catalog = await call(connect, "tekton_catalog", {"project": "/tmp"}, ana_key)
    found = await call(connect, "tekton_find", {"text": "voice"}, ana_key)
    read = await call(connect, "tekton_read", {"session": "s-new", "last": 2}, ana_key)
    updated = await call(connect, "tekton_update", {"session": "s-new", "title": "vad fixed", "tag": "done"}, ana_key)
    peers = await call(connect, "tekton_peers", {}, ana_key)
    receipt = await call(connect, "tekton_send", {"peer": peers["peers"][0]["name"], "text": "hola"}, ana_key)
    assert ([c["name"] for c in catalog["commands"]], [row["session"] for row in found["sessions"]]) == (
        ["research"],
        ["s-new"],
    )
    assert [(t["role"], t["text"]) for t in read["turns"]] == [
        ("tool", "Edit"),
        ("assistant", "Threshold lowered to 0.4; tests green."),
    ]
    assert ((updated["title"], updated["tag"]), receipt["delivered"]) == (("vad fixed", "done"), True)


async def test_tekton_eng_runs_the_shared_grammar(connect: Connect, ana_key: dict[str, str]) -> None:
    listed = await call(connect, "tekton_eng", {"text": "eng ls", "project": "/tmp"}, ana_key)
    assert (listed["verb"], [row["session"] for row in listed["result"]][:1]) == ("list", ["s-new"])


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("tekton_start", {**TASK, "profile": "nope"}, "unknown profile"),
        ("tekton_start", {**TASK, "project": "/etc"}, "outside the roots"),
        ("tekton_start", {**TASK, "project": "no-such-project"}, "no project named"),
        ("tekton_status", {"task": "missing"}, "unknown task"),
        ("tekton_read", {"session": "gone"}, "unknown session"),
        ("tekton_update", {"session": "gone", "title": "x"}, "unknown session"),
        ("tekton_eng", {"text": "eng"}, "empty order"),
    ],
    ids=["profile", "root", "project", "task", "read", "update", "eng"],
)
async def test_tekton_refusal_is_the_tool_error(
    connect: Connect, ana_key: dict[str, str], tool: str, arguments: dict, message: str
) -> None:
    assert message in await refused(connect, tool, arguments, ana_key)


async def test_tekton_needs_a_key(connect: Connect) -> None:
    async with connect() as mcp:
        result = await mcp.call_tool("tekton_tasks", {})
    assert result.is_error


async def test_tekton_hints(connect: Connect) -> None:
    async with connect() as mcp:
        hints = {tool.name: tool.annotations for tool in (await mcp.list_tools()).tools}
    assert {
        name: (hint.read_only_hint, hint.destructive_hint) for name, hint in hints.items() if hint and "tekton" in name
    } == {
        "tekton_eng": (False, False),
        "tekton_start": (False, False),
        "tekton_status": (True, False),
        "tekton_tasks": (True, False),
        "tekton_cancel": (False, True),
        "tekton_catalog": (True, False),
        "tekton_find": (True, False),
        "tekton_read": (True, False),
        "tekton_update": (False, False),
        "tekton_peers": (True, False),
        "tekton_send": (False, False),
    }
