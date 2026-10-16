import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fakes import RecordingNotifier, ScriptedCoder, Settle, Wire

from e_metaxy.logic.bridge import INTERRUPTED, SILENT, Bridge
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.coder import FinishedEvent, StartedEvent
from e_metaxy.models.error import (
    RootDeniedError,
    UnknownCoderError,
    UnknownProfileError,
    UnknownSessionError,
    UnknownTaskError,
)
from e_metaxy.models.profile import CoderKind, Profile
from e_metaxy.models.task import Task, TaskOrder, TaskState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from e_metaxy.adapters.sqlite import SQLiteAdapter


async def test_bridge_start_done(bridge: Bridge, order: TaskOrder, notifier: RecordingNotifier, settle: Settle) -> None:
    task = await settle(bridge, await bridge.start(order))
    assert (task.state, task.session, task.result, task.cost, task.turns) == (TaskState.DONE, "s-1", "pong", 0.01, 1)
    assert [told.state for told in notifier.told] == [TaskState.DONE]


async def test_bridge_start_spec(bridge: Bridge, coder: ScriptedCoder, order: TaskOrder, settle: Settle) -> None:
    await settle(
        bridge, await bridge.start(TaskOrder(prompt="go", profile="code", cwd="/tmp/x", session="s-0", fork=True))
    )
    assert [(s.prompt, s.cwd, s.profile.name, s.session, s.fork) for s in coder.specs] == [
        ("go", "/tmp/x", "code", "s-0", True)
    ]


async def test_bridge_start_home_cwd(
    bridge: Bridge, coder: ScriptedCoder, settle: Settle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", "/tmp")
    task = await settle(bridge, await bridge.start(TaskOrder(prompt="go", profile="code", cwd="~/x")))
    assert [s.cwd for s in coder.specs] == ["/tmp/x"]
    assert task.cwd == "/tmp/x"


@pytest.mark.parametrize(
    ("script", "state", "error"),
    [
        (
            [StartedEvent(session="s"), FinishedEvent(session="s", failed=True, error="max_turns")],
            TaskState.FAILED,
            "max_turns",
        ),
        ([StartedEvent(session="s")], TaskState.FAILED, SILENT),
    ],
    ids=["coder-failed", "silent"],
)
async def test_bridge_start_failed(
    wire: Wire, order: TaskOrder, script: list, state: TaskState, error: str, settle: Settle
) -> None:
    async with wire(ScriptedCoder(script)) as bridge:
        task = await settle(bridge, await bridge.start(order))
    assert (task.state, task.error, task.session) == (state, error, "s")


async def test_bridge_start_raised(wire: Wire, order: TaskOrder, settle: Settle) -> None:
    async with wire(ScriptedCoder([StartedEvent(session="s")], fail=RuntimeError("cli died"))) as bridge:
        task = await settle(bridge, await bridge.start(order))
    assert (task.state, task.error) == (TaskState.FAILED, "RuntimeError('cli died')")


@pytest.mark.parametrize(
    ("order", "error"),
    [
        (TaskOrder(prompt="p", profile="nope", cwd="/tmp"), UnknownProfileError),
        (TaskOrder(prompt="p", profile="research", cwd="/etc"), RootDeniedError),
    ],
    ids=["profile", "root"],
)
async def test_bridge_start_refused(bridge: Bridge, order: TaskOrder, error: type[Exception]) -> None:
    with pytest.raises(error):
        await bridge.start(order)
    assert await bridge.tasks() == []


async def test_bridge_start_unknown_coder(ledger: SQLiteAdapter, book: Mapping[str, Profile], order: TaskOrder) -> None:
    async with Bridge(
        coders={}, notifiers={}, ledger=ledger, profiles=book, projects=ProjectIndex(Path("/tmp")), limit=1
    ) as bridge:
        with pytest.raises(UnknownCoderError):
            await bridge.start(order)


async def test_bridge_start_unentered(wire: Wire, coder: ScriptedCoder, order: TaskOrder) -> None:
    with pytest.raises(RuntimeError, match="not entered"):
        await wire(coder).start(order)


async def test_bridge_cancel(wire: Wire, order: TaskOrder, notifier: RecordingNotifier) -> None:
    coder = ScriptedCoder([StartedEvent(session="s-9")], hold=True)
    async with wire(coder) as bridge:
        task = await bridge.start(order)
        await coder.parked.wait()
        cancelled = await bridge.cancel(task.id)
    assert (cancelled.state, cancelled.session) == (TaskState.CANCELLED, "s-9")
    assert [told.state for told in notifier.told] == [TaskState.CANCELLED]


async def test_bridge_cancel_finished(bridge: Bridge, order: TaskOrder, settle: Settle) -> None:
    task = await settle(bridge, await bridge.start(order))
    assert (await bridge.cancel(task.id)).state is TaskState.DONE


async def test_bridge_status_unknown(bridge: Bridge) -> None:
    with pytest.raises(UnknownTaskError):
        await bridge.status("missing")


async def test_bridge_exit_cancels_running(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder([StartedEvent(session="s")], hold=True)
    async with wire(coder) as bridge:
        task = await bridge.start(order)
        await coder.parked.wait()
    async with wire(coder) as reopened:
        assert (await reopened.status(task.id)).state is TaskState.CANCELLED


async def test_bridge_recover(wire: Wire, ledger: SQLiteAdapter, order: TaskOrder) -> None:
    stale = Task.open(order, CoderKind.CLAUDE).bind("s-7")
    async with wire(ScriptedCoder([])) as bridge:
        await bridge._common_save(stale)
    async with wire(ScriptedCoder([])) as reopened:
        task = await reopened.status(stale.id)
    assert (task.state, task.error, task.session) == (TaskState.FAILED, INTERRUPTED, "s-7")


async def test_bridge_tasks(bridge: Bridge, order: TaskOrder, settle: Settle) -> None:
    born = [await settle(bridge, await bridge.start(order)) for _ in range(3)]
    assert [t.id for t in await bridge.tasks(limit=2)] == [born[2].id, born[1].id]
    assert await bridge.tasks(state=TaskState.FAILED) == []


async def test_bridge_tasks_bounded(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder([StartedEvent(session="s")], hold=True)
    async with wire(coder, limit=1) as bridge:
        first, second = await bridge.start(order), await bridge.start(order)
        await coder.parked.wait()
        await asyncio.sleep(0.05)
        assert len(coder.specs) == 1
        await bridge.cancel(first.id)
        await bridge.cancel(second.id)


async def test_bridge_peers_send(bridge: Bridge) -> None:
    peers = await bridge.peers()
    receipt = await bridge.send(peers[0].name, "hola")
    assert ([p.name for p in peers], receipt.delivered, receipt.peer) == (["e-engineer-bc"], True, "e-engineer-bc")


async def test_bridge_peers_unknown_coder(bridge: Bridge) -> None:
    with pytest.raises(UnknownCoderError):
        await bridge.peers(CoderKind.OPENCODE)


async def test_bridge_find_by_text_and_project(bridge: Bridge) -> None:
    assert [row.session for row in await bridge.find(text="VOICE")] == ["s-new"]
    assert [row.cwd for row in await bridge.find(project="/tmp", limit=1)] == ["/tmp"]
    assert await bridge.find(text="nothing like it") == []


async def test_bridge_read(bridge: Bridge) -> None:
    read = await bridge.read("s-new", last=1)
    assert (read.session.title, [t.text for t in read.turns]) == (
        "fix the voice tests",
        ["Threshold lowered to 0.4; tests green."],
    )
    with pytest.raises(UnknownSessionError):
        await bridge.read("gone")


async def test_bridge_update(bridge: Bridge) -> None:
    updated = await bridge.update("s-new", title="vad fixed", tag="done")
    assert (updated.title, updated.tag) == ("vad fixed", "done")
    with pytest.raises(UnknownSessionError):
        await bridge.update("gone", title="x")


async def test_bridge_catalog(bridge: Bridge) -> None:
    catalog = await bridge.catalog("/tmp")
    assert (catalog.cwd, [c.name for c in catalog.commands]) == ("/tmp", ["research"])
