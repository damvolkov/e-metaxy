"""tests/unit/e_organon/services/tekton/status: tekton/status held until the task ends, one `wait` step per tick — and
never held past its cap or below zero."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.tekton import StatusIn
from e_organon.services.tekton import status as module

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine, TaskOrder
    from e_organon.services.tekton.status import StatusTektonService
    from support.coder import ScriptedCoder
    from support.flow import Answered, Refused


async def test_status_waits_for_the_end(
    status: StatusTektonService, answered: Answered, bridge: BridgeEngine, order: TaskOrder
) -> None:
    started = await bridge.start(order)
    steps, task = await answered(status, StatusIn(task=started.id, wait=5.0))
    assert (steps[0], task.state, task.result, task.session) == ("wait", "done", "pong", "s-1")


async def test_status_streams_a_step_per_tick_while_the_task_runs(
    status: StatusTektonService,
    answered: Answered,
    bridge: BridgeEngine,
    order: TaskOrder,
    coder: ScriptedCoder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coder.hold = True
    monkeypatch.setattr(module, "TICK", 0.05)
    started = await bridge.start(order)
    await coder.parked.wait()
    steps, task = await answered(status, StatusIn(task=started.id, wait=0.12))
    assert (steps, task.state) == (["wait"] * 3, "running")


@pytest.mark.parametrize("wait", [0.0, -3.0], ids=["none", "negative"])
async def test_status_without_a_wait_looks_once(
    status: StatusTektonService, answered: Answered, bridge: BridgeEngine, order: TaskOrder, wait: float
) -> None:
    started = await bridge.start(order)
    steps, task = await answered(status, StatusIn(task=started.id, wait=wait))
    assert (steps, task.id) == (["wait"], started.id)


async def test_status_wait_is_capped(
    status: StatusTektonService,
    answered: Answered,
    bridge: BridgeEngine,
    order: TaskOrder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "WAIT_CAP", 0.0)
    started = await bridge.start(order)
    steps, _ = await answered(status, StatusIn(task=started.id, wait=60.0))
    assert steps == ["wait"]


async def test_status_unknown_task_is_refused(status: StatusTektonService, refused: Refused) -> None:
    assert await refused(status, StatusIn(task="missing")) == ([], "UnknownTaskError")
