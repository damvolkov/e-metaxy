"""tests/unit/e_organon/engines/bridge: tasks started, supervised, cancelled and recovered on a scripted coder over a real
ledger; sessions and tasks found by what a caller copies; the task lifecycle as a transition table."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec
import pytest

from e_organon.engines.bridge import (
    INTERRUPTED,
    KEY,
    SILENT,
    AmbiguousSessionError,
    AmbiguousTaskError,
    BridgeEngine,
    RootDeniedError,
    Task,
    TaskOrder,
    TaskState,
    TaskStateError,
    UnknownCoderError,
    UnknownProfileError,
    UnknownSessionError,
    UnknownTaskError,
)
from e_organon.ops.projects import NamedProjects
from e_organon.ports.coder import CoderKind, FinishedEvent, Profile, StartedEvent
from support.coder import UUID, ScriptedCoder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from e_organon.providers.drivers.store.sqlite import SqliteDriver
    from support.bridge import Settle, Wire


async def test_bridge_start_done(bridge: BridgeEngine, order: TaskOrder, settle: Settle) -> None:
    task = await settle(bridge, await bridge.start(order))
    assert (task.state, task.session, task.result, task.cost, task.turns) == (TaskState.DONE, "s-1", "pong", 0.01, 1)


async def test_bridge_start_spec(bridge: BridgeEngine, coder: ScriptedCoder, settle: Settle) -> None:
    await settle(
        bridge, await bridge.start(TaskOrder(prompt="go", profile="code", cwd="/tmp/x", session="s-new", fork=True))
    )
    assert [(s.prompt, s.cwd, s.profile.name, s.session, s.fork) for s in coder.specs] == [
        ("go", "/tmp/x", "code", "s-new", True)
    ]


async def test_bridge_start_home_cwd(
    bridge: BridgeEngine, coder: ScriptedCoder, settle: Settle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", "/tmp")
    task = await settle(bridge, await bridge.start(TaskOrder(prompt="go", profile="code", cwd="~/x")))
    assert ([s.cwd for s in coder.specs], task.cwd) == (["/tmp/x"], "/tmp/x")


@pytest.mark.parametrize(
    ("script", "state", "error"),
    [
        (
            (StartedEvent(session="s"), FinishedEvent(session="s", failed=True, error="max_turns")),
            TaskState.FAILED,
            "max_turns",
        ),
        ((StartedEvent(session="s"),), TaskState.FAILED, SILENT),
    ],
    ids=["coder-failed", "silent"],
)
async def test_bridge_start_failed(
    wire: Wire, order: TaskOrder, script: tuple, state: TaskState, error: str, settle: Settle
) -> None:
    async with wire(ScriptedCoder(script)) as bridge:
        task = await settle(bridge, await bridge.start(order))
    assert (task.state, task.error, task.session) == (state, error, "s")


async def test_bridge_start_raised(wire: Wire, order: TaskOrder, settle: Settle) -> None:
    async with wire(ScriptedCoder((StartedEvent(session="s"),), fail=RuntimeError("cli died"))) as bridge:
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
async def test_bridge_start_refused(bridge: BridgeEngine, order: TaskOrder, error: type[Exception]) -> None:
    with pytest.raises(error):
        await bridge.start(order)
    assert await bridge.tasks() == []


async def test_bridge_start_unknown_coder(ledger: SqliteDriver, book: Mapping[str, Profile], order: TaskOrder) -> None:
    async with BridgeEngine(
        coders={}, ledger=ledger, profiles=book, projects=NamedProjects(Path("/tmp")), limit=1
    ) as bridge:
        with pytest.raises(UnknownCoderError):
            await bridge.start(order)


async def test_bridge_start_unentered(wire: Wire, coder: ScriptedCoder, order: TaskOrder) -> None:
    with pytest.raises(RuntimeError, match="not entered"):
        await wire(coder).start(order)


async def test_bridge_cancel(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder((StartedEvent(session="s-9"),), hold=True)
    async with wire(coder) as bridge:
        task = await bridge.start(order)
        await coder.parked.wait()
        cancelled = await bridge.cancel(task.id)
    assert (cancelled.state, cancelled.session) == (TaskState.CANCELLED, "s-9")


async def test_bridge_cancel_finished(bridge: BridgeEngine, order: TaskOrder, settle: Settle) -> None:
    task = await settle(bridge, await bridge.start(order))
    assert (await bridge.cancel(task.id)).state is TaskState.DONE


async def test_bridge_status_unknown(bridge: BridgeEngine) -> None:
    with pytest.raises(UnknownTaskError):
        await bridge.status("missing")


async def test_bridge_exit_cancels_running(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder((StartedEvent(session="s"),), hold=True)
    async with wire(coder) as bridge:
        task = await bridge.start(order)
        await coder.parked.wait()
    async with wire(coder) as reopened:
        assert (await reopened.status(task.id)).state is TaskState.CANCELLED


async def test_bridge_recover(wire: Wire, ledger: SqliteDriver, order: TaskOrder) -> None:
    stale = Task.open(order, CoderKind.CLAUDE).bind("s-7")
    await ledger.set(KEY + stale.id, msgspec.json.encode(stale))
    async with wire(ScriptedCoder(())) as reopened:
        task = await reopened.status(stale.id)
    assert (task.state, task.error, task.session) == (TaskState.FAILED, INTERRUPTED, "s-7")


async def test_bridge_tasks(bridge: BridgeEngine, order: TaskOrder, settle: Settle) -> None:
    born = [await settle(bridge, await bridge.start(order)) for _ in range(3)]
    assert [t.id for t in await bridge.tasks(limit=2)] == [born[2].id, born[1].id]
    assert await bridge.tasks(state=TaskState.FAILED) == []


async def test_bridge_tasks_bounded(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder((StartedEvent(session="s"),), hold=True)
    async with wire(coder, limit=1) as bridge:
        first, second = await bridge.start(order), await bridge.start(order)
        await coder.parked.wait()
        await asyncio.sleep(0.05)
        assert len(coder.specs) == 1
        await bridge.cancel(first.id)
        await bridge.cancel(second.id)


async def test_bridge_watch_ends_with_the_task(bridge: BridgeEngine, order: TaskOrder) -> None:
    seen = [task async for task in bridge.watch((await bridge.start(order)).id, wait=5.0, tick=1.0)]
    assert (seen[-1].state, all(not task.terminal for task in seen[:-1])) == (TaskState.DONE, True)


async def test_bridge_watch_gives_up_when_the_wait_is_spent(wire: Wire, order: TaskOrder) -> None:
    coder = ScriptedCoder((StartedEvent(session="s"),), hold=True)
    async with wire(coder) as bridge:
        task = await bridge.start(order)
        await coder.parked.wait()
        seen = [each async for each in bridge.watch(task.id, wait=0.25, tick=0.1)]
        await bridge.cancel(task.id)
    assert ([each.state for each in seen], len(seen)) == ([TaskState.RUNNING] * 3, 3)


async def test_bridge_watch_without_a_wait_looks_once(bridge: BridgeEngine, order: TaskOrder) -> None:
    seen = [task async for task in bridge.watch((await bridge.start(order)).id, wait=0.0, tick=1.0)]
    assert len(seen) == 1


async def test_bridge_peers_send(bridge: BridgeEngine) -> None:
    peers = await bridge.peers()
    receipt = await bridge.send(peers[0].name, "hola")
    assert ([p.name for p in peers], receipt.delivered, receipt.peer) == (["e-engineer-bc"], True, "e-engineer-bc")


async def test_bridge_peers_unknown_coder(bridge: BridgeEngine) -> None:
    with pytest.raises(UnknownCoderError):
        await bridge.peers(CoderKind.OPENCODE)


async def test_bridge_find_by_text_and_project(bridge: BridgeEngine) -> None:
    assert [row.session for row in await bridge.find(text="VOICE")] == ["s-new"]
    assert [row.cwd for row in await bridge.find(project="/tmp", limit=1)] == ["/tmp"]
    assert await bridge.find(text="nothing like it") == []


async def test_bridge_read(bridge: BridgeEngine) -> None:
    read = await bridge.read("s-new", last=1)
    assert (read.session.title, [t.text for t in read.turns]) == (
        "fix the voice tests",
        ["Threshold lowered to 0.4; tests green."],
    )
    with pytest.raises(UnknownSessionError):
        await bridge.read("gone")


async def test_bridge_update(bridge: BridgeEngine) -> None:
    updated = await bridge.update("s-new", title="vad fixed", tag="done")
    assert (updated.title, updated.tag) == ("vad fixed", "done")
    with pytest.raises(UnknownSessionError):
        await bridge.update("gone", title="x")


async def test_bridge_catalog(bridge: BridgeEngine) -> None:
    catalog = await bridge.catalog("/tmp")
    assert (catalog.cwd, [c.name for c in catalog.commands]) == ("/tmp", ["research"])


@pytest.mark.parametrize(
    "ref",
    [UUID, "7b4fb561", "7b4fb561-4dde-463f-54b-e8c9114b3682", "tools mcp en tools.py", f"  {UUID} "],
    ids=["id", "prefix", "mangled", "title", "padded"],
)
async def test_bridge_read_resolves_what_a_caller_copies(bridge: BridgeEngine, ref: str) -> None:
    assert (await bridge.read(ref, last=1)).session.session == UUID


async def test_bridge_ambiguous_prefix_names_the_candidates(bridge: BridgeEngine) -> None:
    with pytest.raises(AmbiguousSessionError, match="7b4fb5ff-twin"):
        await bridge.read("7b4fb5")
    with pytest.raises(UnknownSessionError):
        await bridge.read("7b4f")


async def test_bridge_update_by_title(bridge: BridgeEngine) -> None:
    updated = await bridge.update("Tools MCP en tools.py", tag="drill")
    assert (updated.session, updated.tag) == (UUID, "drill")


async def test_bridge_start_resumes_by_prefix_and_refuses_an_unknown_session(
    bridge: BridgeEngine, coder: ScriptedCoder, settle: Settle
) -> None:
    await settle(bridge, await bridge.start(TaskOrder(prompt="go", profile="code", cwd="/tmp/x", session="7b4fb561")))
    assert [s.session for s in coder.specs] == [UUID]
    with pytest.raises(UnknownSessionError):
        await bridge.start(TaskOrder(prompt="go", profile="code", cwd="/tmp/x", session="nope"))


async def test_bridge_task_by_head_or_tail(bridge: BridgeEngine, order: TaskOrder, settle: Settle) -> None:
    first = await settle(bridge, await bridge.start(order))
    second = await settle(bridge, await bridge.start(order))
    assert (await bridge.status(first.id[-8:])).id == first.id
    assert (await bridge.status(f"  {second.id} ")).id == second.id
    with pytest.raises(AmbiguousTaskError, match="several tasks"):
        await bridge.status(first.id[:6])
    with pytest.raises(UnknownTaskError):
        await bridge.status("zzzzzzzz")
    with pytest.raises(UnknownTaskError):
        await bridge.status("abc")


##### TASK #####


async def test_task_open(order: TaskOrder) -> None:
    task = Task.open(msgspec.structs.replace(order, session="s-1", fork=True), CoderKind.CLAUDE)
    assert (task.state, task.parent, task.fork, task.session) == (TaskState.RUNNING, "s-1", True, "")


async def test_task_open_ids_sort_by_birth(order: TaskOrder) -> None:
    ids = [Task.open(order, CoderKind.CLAUDE).id for _ in range(32)]
    assert ids == sorted(ids)


@pytest.mark.parametrize("state", [TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED])
async def test_task_move(order: TaskOrder, state: TaskState) -> None:
    task = Task.open(order, CoderKind.CLAUDE).move(state, result="r")
    assert (task.state, task.result, task.terminal) == (state, "r", True)


@pytest.mark.parametrize("state", list(TaskState))
async def test_task_move_from_terminal(order: TaskOrder, state: TaskState) -> None:
    with pytest.raises(TaskStateError):
        Task.open(order, CoderKind.CLAUDE).move(TaskState.DONE).move(state)


async def test_task_bind(order: TaskOrder) -> None:
    task = Task.open(order, CoderKind.CLAUDE).bind("s-2")
    assert (task.session, task.state, task.terminal) == ("s-2", TaskState.RUNNING, False)
