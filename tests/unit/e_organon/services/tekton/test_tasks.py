"""tests/unit/e_organon/services/tekton/tasks: tekton/tasks lists the ledger newest first, of one state or all."""

from typing import TYPE_CHECKING

from e_organon.models.tekton import TasksIn

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine, TaskOrder
    from e_organon.services.tekton.tasks import TasksTektonService
    from support.bridge import Settle
    from support.flow import Answered


async def test_tasks_newest_first_of_one_state(
    tasks: TasksTektonService, answered: Answered, bridge: BridgeEngine, order: TaskOrder, settle: Settle
) -> None:
    born = [await settle(bridge, await bridge.start(order)) for _ in range(3)]
    steps, listed = await answered(tasks, TasksIn(limit=2))
    _, failed = await answered(tasks, TasksIn(state="failed"))
    _, done = await answered(tasks, TasksIn(state="done"))
    assert (steps, [task.id for task in listed.tasks], failed.tasks, len(done.tasks)) == (
        ["list"],
        [born[2].id, born[1].id],
        [],
        3,
    )
