"""tests/unit/e_organon/services/tekton/cancel: tekton/cancel interrupts a running task; a finished one comes back as it
was; an unknown one is refused."""

from typing import TYPE_CHECKING

from e_organon.models.tekton import CancelIn

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine, TaskOrder
    from e_organon.services.tekton.cancel import CancelTektonService
    from support.bridge import Settle
    from support.coder import ScriptedCoder
    from support.flow import Answered, Refused


async def test_cancel_interrupts_a_running_task(
    cancel: CancelTektonService, answered: Answered, bridge: BridgeEngine, order: TaskOrder, coder: ScriptedCoder
) -> None:
    coder.hold = True
    started = await bridge.start(order)
    await coder.parked.wait()
    steps, task = await answered(cancel, CancelIn(task=started.id))
    assert (steps, task.state, task.session) == (["cancel"], "cancelled", "s-1")


async def test_cancel_a_finished_task_is_unchanged(
    cancel: CancelTektonService, answered: Answered, bridge: BridgeEngine, order: TaskOrder, settle: Settle
) -> None:
    done = await settle(bridge, await bridge.start(order))
    _, task = await answered(cancel, CancelIn(task=done.id))
    assert task.state == "done"


async def test_cancel_unknown_task_is_refused(cancel: CancelTektonService, refused: Refused) -> None:
    assert await refused(cancel, CancelIn(task="missing")) == (["cancel"], "UnknownTaskError")
