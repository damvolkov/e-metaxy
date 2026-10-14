import pytest

from e_metaxy.models.error import TaskStateError
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import Task, TaskOrder, TaskState


@pytest.fixture
def order() -> TaskOrder:
    return TaskOrder(prompt="ping", profile="research", cwd="/tmp", session="s-1", fork=True, caller="openhuman")


async def test_task_open(order: TaskOrder) -> None:
    task = Task.open(order, CoderKind.CLAUDE)
    assert (task.state, task.parent, task.fork, task.caller, task.session) == (
        TaskState.RUNNING,
        "s-1",
        True,
        "openhuman",
        "",
    )


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
