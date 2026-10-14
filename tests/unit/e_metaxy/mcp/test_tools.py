from typing import TYPE_CHECKING

import pytest

from e_metaxy.models.task import TaskState

if TYPE_CHECKING:
    from fakes import Connect


async def test_tools_listed(connect: Connect) -> None:
    async with connect() as client:
        listed = await client.list_tools()
        assert sorted(tool.name for tool in listed.tools) == [
            "profile_list",
            "session_history",
            "session_list",
            "session_send",
            "task_cancel",
            "task_list",
            "task_start",
            "task_status",
        ]


async def test_tools_history(connect: Connect) -> None:
    async with connect() as client:
        rows = (await client.call_tool("session_history", {"cwd": "/tmp", "limit": 5})).structured_content["result"]
        assert [(r["session"], r["title"], r["cwd"]) for r in rows] == [("s-old", "earlier work", "/tmp")]


async def test_tools_task_flow(connect: Connect) -> None:
    async with connect() as client:
        started = await client.call_tool("task_start", {"prompt": "ping", "profile": "research", "cwd": "/tmp"})
        task = started.structured_content
        assert (started.is_error, task["state"]) == (False, TaskState.RUNNING)
        status = (await client.call_tool("task_status", {"task": task["id"], "wait": 2})).structured_content
        listed = await client.call_tool("task_list", {"limit": 5})
        assert (status["state"], status["result"], [t["id"] for t in listed.structured_content["result"]]) == (
            "done",
            "pong",
            [task["id"]],
        )


async def test_tools_task_cancel_finished(connect: Connect) -> None:
    async with connect() as client:
        task = (
            await client.call_tool("task_start", {"prompt": "p", "profile": "research", "cwd": "/tmp"})
        ).structured_content
        await client.call_tool("task_status", {"task": task["id"], "wait": 2})
        assert (await client.call_tool("task_cancel", {"task": task["id"]})).structured_content["state"] == "done"


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("task_start", {"prompt": "p", "profile": "nope", "cwd": "/tmp"}, "unknown profile"),
        ("task_start", {"prompt": "p", "profile": "research", "cwd": "/etc"}, "outside the roots"),
        ("task_status", {"task": "missing"}, "unknown task"),
        ("session_list", {"coder": "opencode"}, "no coder serves"),
    ],
    ids=["profile", "root", "task", "coder"],
)
async def test_tools_refused(connect: Connect, tool: str, arguments: dict, message: str) -> None:
    async with connect() as client:
        result = await client.call_tool(tool, arguments)
        assert result.is_error
        assert message in str(result.content)


async def test_tools_sessions(connect: Connect) -> None:
    async with connect() as client:
        sessions = (await client.call_tool("session_list", {})).structured_content["result"]
        receipt = (
            await client.call_tool("session_send", {"peer": sessions[0]["name"], "text": "hola"})
        ).structured_content
        assert ([s["status"] for s in sessions], receipt["delivered"]) == (["busy"], True)


async def test_tools_profiles(connect: Connect) -> None:
    async with connect() as client:
        profiles = (await client.call_tool("profile_list", {})).structured_content["result"]
        assert sorted((p["name"], p["mode"]) for p in profiles) == [
            ("code", "acceptEdits"),
            ("direct", "bypassPermissions"),
            ("research", "dontAsk"),
        ]
