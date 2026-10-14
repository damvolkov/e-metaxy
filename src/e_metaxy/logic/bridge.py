"""e_metaxy.logic.bridge: the in-between — orders in, runs supervised, results recorded and called back.

Every run lives in one TaskGroup, bounded by a semaphore; every transition is written to the ledger before
anyone can read it; a run that ends tells its caller. The bridge knows ports only: which coder, which
notifier and which store sit behind them is the composition root's business."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType
from typing import Final, Self

import anyio
import msgspec
import structlog
from beartype import beartype

from adapters.ports import StorePort
from e_metaxy.logic.ports import CoderPort, NotifierPort
from e_metaxy.models.coder import CoderPeer, CoderReceipt, CoderSession, CoderSpec, FinishedEvent, StartedEvent
from e_metaxy.models.error import RootDeniedError, UnknownCoderError, UnknownProfileError, UnknownTaskError
from e_metaxy.models.profile import CoderKind, Profile
from e_metaxy.models.task import Task, TaskOrder, TaskState

log = structlog.get_logger()

KEY: Final = "task:"
INTERRUPTED: Final = "interrupted: the bridge restarted while the task ran; resume its session"
SILENT: Final = "the coder ended without a result"


@beartype
class Bridge:
    """Starts, supervises, cancels and lists tasks across coders; recovers what a restart cut short."""

    __slots__ = ("_coders", "_gate", "_group", "_ledger", "_notifiers", "_profiles", "_runs", "_stack")

    def __init__(
        self,
        *,
        coders: Mapping[CoderKind, CoderPort],
        notifiers: Mapping[str, NotifierPort],
        ledger: StorePort,
        profiles: Mapping[str, Profile],
        limit: int,
    ) -> None:
        self._coders = coders
        self._notifiers = notifiers
        self._ledger = ledger
        self._profiles = profiles
        self._gate = asyncio.Semaphore(limit)
        self._runs: dict[str, asyncio.Task[None]] = {}
        self._stack = AsyncExitStack()
        self._group: asyncio.TaskGroup | None = None

    ##### PRIVATE METHODS #####

    async def _common_save(self, task: Task) -> Task:
        await self._ledger.set(KEY + task.id, msgspec.json.encode(task, enc_hook=Task.enc_hook))
        return task

    async def _common_load(self, task: str) -> Task:
        match await self._ledger.get(KEY + task):
            case None:
                raise UnknownTaskError(task)
            case raw:
                return Task.convert(msgspec.json.decode(raw), Task)

    def _common_group(self) -> asyncio.TaskGroup:
        match self._group:
            case None:
                msg = "Bridge not entered: the lifespan opens it, tools never do"
                raise RuntimeError(msg)
            case group:
                return group

    def _start_profile(self, order: TaskOrder) -> Profile:
        match self._profiles.get(order.profile):
            case None:
                raise UnknownProfileError(order.profile, tuple(self._profiles))
            case profile:
                return profile

    def _common_coder(self, coder: CoderKind) -> CoderPort:
        match self._coders.get(coder):
            case None:
                raise UnknownCoderError(coder)
            case port:
                return port

    async def _start_root(self, order: TaskOrder, profile: Profile) -> None:
        """The cwd must live under a root of the profile — resolved off the loop, it touches the filesystem."""
        match await anyio.to_thread.run_sync(profile.admits, Path(order.cwd)):
            case False:
                raise RootDeniedError(order.cwd, order.profile)

    async def _start_finish(self, task: Task, event: FinishedEvent) -> Task:
        state = TaskState.FAILED if event.failed else TaskState.DONE
        return await self._common_save(
            task.move(
                state,
                session=event.session or task.session,
                result=event.result,
                error=event.error,
                cost=event.cost,
                turns=event.turns,
            )
        )

    async def _start_run(self, task: Task, coder: CoderPort, spec: CoderSpec) -> None:
        """One supervised run: events advance the ledger; any failure becomes a failed task, never a crash."""
        try:
            async with self._gate:
                task = await self._start_drive(task, coder, spec)
        except asyncio.CancelledError:
            ### the ledger holds what the drive learnt (its session): the local value is the one it started with.
            task = await self._common_save((await self._common_load(task.id)).move(TaskState.CANCELLED))
            await self._start_notify(task)
            raise
        except Exception as exc:  # noqa: BLE001 — the run boundary: a coder failure is the task's, not the bridge's
            log.warning("TASK_FAILED", task=task.id, error=repr(exc))
            task = await self._common_save((await self._common_load(task.id)).move(TaskState.FAILED, error=repr(exc)))
        await self._start_notify(task)

    async def _start_drive(self, task: Task, coder: CoderPort, spec: CoderSpec) -> Task:
        async for event in coder.run(spec):
            match event:
                case StartedEvent(session=session):
                    task = await self._common_save(task.bind(session))
                case finished:
                    return await self._start_finish(task, finished)
        return await self._common_save(task.move(TaskState.FAILED, error=SILENT))

    async def _start_notify(self, task: Task) -> None:
        match self._notifiers.get(task.caller):
            case None:
                return
            case notifier:
                await notifier.notify(task)

    async def _common_recover(self) -> int:
        """Tasks a restart cut short become failed with their session kept; returns how many."""
        stale = [task async for task in self._common_scan() if task.state is TaskState.RUNNING]
        _ = [await self._common_save(task.move(TaskState.FAILED, error=INTERRUPTED)) for task in stale]
        return len(stale)

    async def _common_scan(self) -> AsyncIterator[Task]:
        """Every task in the ledger, oldest first — uuid7 keys sort by birth."""
        async for key in self._ledger.keys(KEY):
            yield await self._common_load(key.removeprefix(KEY))

    ############################################################

    ##### LIFECYCLE #####

    async def __aenter__(self) -> Self:
        self._group = await self._stack.enter_async_context(asyncio.TaskGroup())
        log.info("BRIDGE_OPEN", recovered=await self._common_recover(), profiles=len(self._profiles))
        return self

    async def __aexit__(
        self, _exc_type: type[BaseException] | None, _exc: BaseException | None, _tb: TracebackType | None
    ) -> None:
        _ = [run.cancel() for run in self._runs.values()]
        await self._stack.aclose()
        self._group = None

    ##### PUBLIC #####

    async def start(self, order: TaskOrder) -> Task:
        """A running task for the order; the run proceeds in the background."""
        profile = self._start_profile(order)
        coder = self._common_coder(profile.coder)
        await self._start_root(order, profile)
        task = await self._common_save(Task.open(order, profile.coder))
        spec = CoderSpec(prompt=order.prompt, cwd=order.cwd, profile=profile, session=order.session, fork=order.fork)
        run = self._common_group().create_task(self._start_run(task, coder, spec), name=f"task:{task.id}")
        self._runs[task.id] = run
        run.add_done_callback(lambda _: self._runs.pop(task.id, None))
        log.info("TASK_STARTED", task=task.id, profile=profile.name, coder=profile.coder, resume=bool(order.session))
        return task

    async def status(self, task: str, wait: float = 0.0) -> Task:
        """The task now — or, with `wait` seconds, once it ends or the wait runs out, whichever comes first."""
        match self._runs.get(task):
            case asyncio.Task() as run if wait > 0:
                await asyncio.wait({run}, timeout=wait)
        return await self._common_load(task)

    async def cancel(self, task: str) -> Task:
        """The task after cancellation; a task already ended is returned as it is."""
        match self._runs.get(task):
            case asyncio.Task() as run:
                run.cancel()
                await asyncio.wait({run})
        return await self._common_load(task)

    async def tasks(self, state: TaskState | None = None, limit: int = 20) -> list[Task]:
        """The newest `limit` tasks, optionally of one state — newest first."""
        matching = [task async for task in self._common_scan() if state is None or task.state is state]
        return matching[::-1][:limit]

    async def peers(self, coder: CoderKind = CoderKind.CLAUDE) -> list[CoderPeer]:
        return await self._common_coder(coder).peers()

    async def send(self, peer: str, text: str, coder: CoderKind = CoderKind.CLAUDE) -> CoderReceipt:
        return await self._common_coder(coder).send(peer, text)

    async def history(self, cwd: str, coder: CoderKind = CoderKind.CLAUDE, limit: int = 25) -> list[CoderSession]:
        return await self._common_coder(coder).history(cwd, limit)

    async def profiles(self) -> list[Profile]:
        return list(self._profiles.values())
