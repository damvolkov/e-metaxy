"""e_organon.services.jobs: the tools as jobs — each a kind of the dispatch, run in the background and read by its id.

Every tool of a section is a kind named `<section>/<word>` (`doc/convert`) on its section's queue. A job's work is the
tool's own workflow: the stored arguments decoded into the tool's input, its `Step`s reported as progress, its answer
(`done`) or its failure (`failed`) reported last — a failure also raised, so the job settles `failed`, once. The
progress is cumulative (`steps` holds every step so far): a snapshot written at most every throttle, and always once at
the end, still tells all that happened, so a reader that polls misses nothing. A job's arguments are the tool's input
as builtins under one key, `input`, beside `owner`, the account that queued it: the dispatch's own names (`attempts`,
`coalesce`, `_trace`) can never meet a field of a tool's input. A job is its owner's: for any other caller it does not
exist (`UnknownJobError`, never a refusal that would reveal it); the admin reaches every job.

`status` reads a job, held up to `wait` seconds until it settles; `events` replays it as the events a stream of the tool
would have told, polled until it settles; `cancel` stops it. A job unknown to the dispatch is `UnknownJobError`."""

from collections import deque
from functools import partial
from typing import TYPE_CHECKING, Any, Self

import anyio
import msgspec

from e_organon.infra.auth.models import Role
from e_organon.infra.background import SETTLED, BackgroundJob, BackgroundState
from e_organon.models.error import FlowError, UnknownJobError, UnknownToolError
from e_organon.models.flow import Done, Event, Failed, Step
from e_organon.models.job import AcceptedJob, Job

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    from e_organon.engines.dispatch import DispatchEngine
    from e_organon.infra.auth.models import Caller
    from e_organon.infra.background import BackgroundReporter, BackgroundWork
    from e_organon.services.flow import ToolFlow


##### WATCH #####
class WatchJobsService:
    """A job's events as they happen, one per call: the steps it has entered, then how it ended. A poll that finds
    nothing new answers `None` — the caller's tick — and the iteration ends once the job has settled and been told."""

    __slots__ = ("_first", "_job", "_pending", "_poll", "_read", "_seen", "_settled")

    def __init__(self, read: Callable[[str], Awaitable[BackgroundJob]], job: str, poll: float) -> None:
        self._read, self._job, self._poll = read, job, poll
        self._pending: deque[Event] = deque()
        self._seen, self._first, self._settled = 0, True, False

    ##### PRIVATE #####

    @staticmethod
    def _anext_end(job: BackgroundJob) -> Event:
        """How a settled job ended: the answer or the failure it reported, else what the queue knows of it."""
        match (job.progress or {}, job.state):
            case ({"done": result}, _):
                return Done(result=result)
            case ({"failed": {"kind": kind, "reason": reason}}, _):
                return Failed(kind=kind, reason=reason)
            case (_, BackgroundState.CANCELLED):
                return Failed(kind="Cancelled", reason="the job was cancelled")
            case _:
                return Failed(kind="JobFailed", reason=job.errors[-1] if job.errors else "settled without an answer")

    async def _anext_poll(self) -> None:
        """One read of the job, after a poll's wait (none before the first): its new steps, and its end if it settled."""
        await anyio.sleep(0 if self._first else self._poll)
        job = await self._read(self._job)
        steps = (job.progress or {}).get("steps", [])
        self._first, self._settled = False, job.state in SETTLED
        self._pending.extend(Step(**each) for each in steps[self._seen :])
        self._pending.extend([self._anext_end(job)] if self._settled else [])
        self._seen = len(steps)

    ############################################################

    ##### PUBLIC #####

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Event | None:
        match (bool(self._pending), self._settled):
            case (False, True):
                raise StopAsyncIteration
            case (False, False):
                await self._anext_poll()
            case _:
                pass
        return self._pending.popleft() if self._pending else None


##### SERVICE #####
class JobsService:
    """The tools of the sections as kinds of the dispatch, and the jobs they make."""

    __slots__ = ("_dispatch", "_kinds", "_poll", "_tools")

    def __init__(self, dispatch: DispatchEngine, tools: Mapping[str, ToolFlow[Any, Any]], *, poll: float) -> None:
        self._dispatch, self._poll = dispatch, poll
        self._tools = tools
        self._kinds = {tool: kind for kind, tool in tools.items()}

    ##### PRIVATE #####

    async def _status_read(self, job: str, caller: Caller) -> BackgroundJob:
        """The job if it is the caller's — or the caller is the admin —, else it is unknown."""
        match found := await self._dispatch.job(job):
            case BackgroundJob() if caller.role is Role.ADMIN or found.args.get("owner") == caller.owner:
                return found
            case _:
                raise UnknownJobError(job)

    @staticmethod
    async def _register_events(tool: ToolFlow[Any, Any], args: Mapping[str, Any]) -> AsyncIterator[Event]:
        """The tool's events over the stored arguments; arguments it cannot read are its first and only event, `Failed`."""
        try:
            data = msgspec.convert(args.get("input", {}), tool.arguments())
        except msgspec.ValidationError as error:
            yield Failed(kind=type(error).__name__, reason=str(error))
        else:
            async for event in tool.events(data):
                yield event

    def _register_work(self, tool: ToolFlow[Any, Any]) -> BackgroundWork:
        async def work(args: Mapping[str, Any], report: BackgroundReporter) -> None:
            steps: list[dict[str, Any]] = []
            async for event in self._register_events(tool, args):
                progress = {"step": steps[-1] if steps else None, "steps": list(steps)}
                match event:
                    case Step():
                        steps.append(msgspec.structs.asdict(event))
                        await report({"step": steps[-1], "steps": list(steps)})
                    case Done(result=result):
                        await report(progress | {"done": msgspec.to_builtins(result)})
                    case failed:
                        await report(progress | {"failed": msgspec.structs.asdict(failed)})
                        raise FlowError(failed)

        return work

    ############################################################

    ##### PUBLIC #####

    @property
    def kinds(self) -> dict[str, str]:
        """Every kind and the queue it runs on: its section."""
        return {kind: kind.partition("/")[0] for kind in self._tools}

    def accepts(self, tool: ToolFlow[Any, Any]) -> bool:
        """Whether the tool is a kind: the tekton tools, and any other the root left out, are not."""
        return tool in self._kinds

    def register(self, slots: Mapping[str, int]) -> None:
        """Declare each section's queue with its `slots` and bind every tool to it; before the dispatch is entered."""
        _ = [self._dispatch.queue(section, count) for section, count in slots.items()]
        _ = [
            self._dispatch.register(kind, self._register_work(tool), queue=queue)
            for (kind, queue), tool in zip(self.kinds.items(), self._tools.values(), strict=True)
        ]

    async def submit(self, tool: ToolFlow[Any, Any], data: msgspec.Struct, caller: Caller) -> AcceptedJob:
        """The tool queued over `data` for the caller, at once."""
        job = await self._dispatch.submit(self._kinds[tool], owner=caller.owner, input=msgspec.to_builtins(data))
        return AcceptedJob(job=job.id, state=job.state)

    async def enqueue(self, tool: str, arguments: Mapping[str, Any], caller: Caller) -> AcceptedJob:
        """The tool named `<section>/<word>` queued over `arguments`, once it reads as the tool's own input: what a client that
        cannot send `Prefer` asks for. A tool that is no job is `UnknownToolError`, arguments that miss its Struct
        `msgspec.ValidationError` — both before anything is queued."""
        match self._tools.get(tool):
            case None:
                raise UnknownToolError(tool)
            case found:
                return await self.submit(found, msgspec.convert(arguments, found.arguments()), caller)

    async def status(self, job: str, caller: Caller, wait: float = 0.0) -> Job:
        """The job now, or once it settles if that comes within `wait` seconds."""
        with anyio.move_on_after(wait):
            async for _ in self.events(job, caller):
                pass
        return Job.of(await self._status_read(job, caller))

    async def events(self, job: str, caller: Caller) -> AsyncIterator[Event]:
        """The job's steps as it enters them, then its answer or why not, polled until it settles."""
        async for event in WatchJobsService(partial(self._status_read, caller=caller), job, self._poll):
            match event:
                case None:
                    pass
                case _:
                    yield event

    async def cancel(self, job: str, caller: Caller) -> Job:
        """The job stopped where it awaits; one already settled comes back as it is."""
        held = await self._status_read(job, caller)
        ### a job settled and gone between the check and the cancel comes back as the check found it.
        return Job.of(await self._dispatch.cancel(job) or held)
