"""tests/unit/e_organon/services/jobs: every tool a kind of its section's queue; a job streams the steps of its tool and
settles with its answer, or with why not — read by status (held when asked to wait) and by events (polled until settled)."""

from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Final

import pytest

from e_organon.infra.background import BackgroundState
from e_organon.models.error import UnknownJobError
from e_organon.models.flow import Done, Failed, Step
from e_organon.models.job import AcceptedJob
from e_organon.services.jobs import JobsService
from support.tools import BoomTool, ShoutTool, SlowTool, WordIn

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from e_organon.engines.dispatch import DispatchEngine
    from e_organon.infra.auth.models import Caller

type Jobs = AbstractAsyncContextManager[JobsService]

### each way to ask for a job, awaited on the service: the first thing it does is refuse an id nobody holds.
READS: Final[dict[str, Callable[[JobsService, Caller, str], Awaitable[object]]]] = {
    "status": lambda service, caller, job: service.status(job, caller),
    "cancel": lambda service, caller, job: service.cancel(job, caller),
    "events": lambda service, caller, job: anext(service.events(job, caller)),
}


async def test_jobs_register_one_kind_per_tool_on_its_sections_queue(jobs: Jobs) -> None:
    async with jobs as service:
        assert service.kinds == {"doc/shout": "doc", "doc/boom": "doc", "doc/slow": "doc"}


async def test_jobs_accepts_a_registered_tool_only(jobs: Jobs, shout: ShoutTool) -> None:
    async with jobs as service:
        assert (service.accepts(shout), service.accepts(ShoutTool())) == (True, False)


async def test_jobs_submit_answers_at_once_with_the_job(jobs: Jobs, shout: ShoutTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(shout, WordIn(text="hola"), ana)
    assert (isinstance(accepted, AcceptedJob), accepted.state) == (True, BackgroundState.AVAILABLE)


async def test_jobs_status_waits_for_the_answer(jobs: Jobs, shout: ShoutTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(shout, WordIn(text="hola"), ana)
        job = await service.status(accepted.job, ana, wait=5.0)
    assert (job.kind, job.state, job.errors) == ("doc/shout", BackgroundState.COMPLETED, [])
    assert job.progress == {
        "step": {"name": "shout", "index": 1, "total": 2},
        "steps": [{"name": "read", "index": 0, "total": 2}, {"name": "shout", "index": 1, "total": 2}],
        "done": {"shouted": "HOLA"},
    }


async def test_jobs_status_without_a_wait_answers_as_it_stands(jobs: Jobs, slow: SlowTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(slow, WordIn(text="x"), ana)
        job = await service.status(accepted.job, ana)
        _ = await service.cancel(accepted.job, ana)
    assert job.state in {BackgroundState.AVAILABLE, BackgroundState.RUNNING}


async def test_jobs_events_replay_the_steps_then_the_answer(jobs: Jobs, shout: ShoutTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(shout, WordIn(text="hola"), ana)
        events = [event async for event in service.events(accepted.job, ana)]
    assert events == [
        Step(name="read", index=0, total=2),
        Step(name="shout", index=1, total=2),
        Done(result={"shouted": "HOLA"}),
    ]


async def test_jobs_failure_settles_failed_with_why(jobs: Jobs, boom: BoomTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(boom, WordIn(text="boom"), ana)
        events = [event async for event in service.events(accepted.job, ana)]
        job = await service.status(accepted.job, ana)
    assert events == [Step(name="read", index=0, total=1), Failed(kind="ValueError", reason="boom")]
    assert (job.state, [error.startswith("FlowError") for error in job.errors]) == (BackgroundState.FAILED, [True])
    assert job.progress is not None
    assert job.progress["failed"] == {"kind": "ValueError", "reason": "boom"}


async def test_jobs_arguments_the_tool_cannot_read_fail_the_job(
    jobs: Jobs, dispatch: DispatchEngine, ana: Caller
) -> None:
    ### the job a stale queue could hold: arguments of another shape than the tool's.
    async with jobs as service:
        stale = await dispatch.submit("doc/shout", owner=ana.owner, input={"text": 3})
        events = [event async for event in service.events(stale.id, ana)]
    assert [(type(event), getattr(event, "kind", "")) for event in events] == [(Failed, "ValidationError")]


async def test_jobs_a_worker_lost_without_a_word_is_told_from_the_queue(
    jobs: Jobs, dispatch: DispatchEngine, ana: Caller
) -> None:
    async with jobs as service:
        lost = await dispatch.submit("doc/crash", owner=ana.owner)
        events = [event async for event in service.events(lost.id, ana)]
    assert events == [Failed(kind="JobFailed", reason="RuntimeError: worker lost")]


async def test_jobs_cancel_settles_cancelled(jobs: Jobs, slow: SlowTool, ana: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(slow, WordIn(text="x"), ana)
        stream = service.events(accepted.job, ana)
        first = await anext(stream)
        cancelled = await service.cancel(accepted.job, ana)
        rest = [event async for event in stream]
    assert (first, cancelled.state, rest) == (
        Step(name="read", index=0, total=1),
        BackgroundState.CANCELLED,
        [Failed(kind="Cancelled", reason="the job was cancelled")],
    )


@pytest.mark.parametrize("read", sorted(READS))
async def test_jobs_unknown_job_is_refused(jobs: Jobs, ana: Caller, read: str) -> None:
    async with jobs as service:
        with pytest.raises(UnknownJobError, match="nope"):
            await READS[read](service, ana, "nope")


@pytest.mark.parametrize("read", sorted(READS))
async def test_jobs_another_accounts_job_is_unknown_to_a_caller(
    jobs: Jobs, shout: ShoutTool, ana: Caller, bob: Caller, read: str
) -> None:
    async with jobs as service:
        accepted = await service.submit(shout, WordIn(text="hola"), ana)
        with pytest.raises(UnknownJobError, match=accepted.job):
            await READS[read](service, bob, accepted.job)


async def test_jobs_the_admin_reads_and_cancels_any_job(jobs: Jobs, slow: SlowTool, ana: Caller, root: Caller) -> None:
    async with jobs as service:
        accepted = await service.submit(slow, WordIn(text="x"), ana)
        read = await service.status(accepted.job, root)
        stopped = await service.cancel(accepted.job, root)
    assert (read.id, stopped.state) == (accepted.job, BackgroundState.CANCELLED)


async def test_jobs_the_tool_input_is_one_key_of_the_arguments(
    jobs: Jobs, shout: ShoutTool, ana: Caller, dispatch: DispatchEngine
) -> None:
    ### so no field of a tool's input can meet the dispatch's own names (`attempts`, `coalesce`, `_trace`).
    async with jobs as service:
        accepted = await service.submit(shout, WordIn(text="a"), ana)
        held = await dispatch.job(accepted.job)
    assert held is not None
    assert set(held.args) == {"owner", "input"}
