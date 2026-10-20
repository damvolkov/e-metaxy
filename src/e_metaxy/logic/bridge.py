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

from e_metaxy.adapters.ports import StorePort
from e_metaxy.logic.ports import CoderPort, NotifierPort
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.coder import (
    CoderCatalog,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    SessionRead,
    StartedEvent,
)
from e_metaxy.models.error import (
    AmbiguousSessionError,
    AmbiguousTaskError,
    RootDeniedError,
    UnknownCoderError,
    UnknownProfileError,
    UnknownSessionError,
    UnknownTaskError,
)
from e_metaxy.models.profile import CoderKind, Profile
from e_metaxy.models.task import Task, TaskOrder, TaskState

log = structlog.get_logger()

KEY: Final = "task:"
INTERRUPTED: Final = "interrupted: the bridge restarted while the task ran; resume its session"
SILENT: Final = "the coder ended without a result"
### the sessions a prefix or a title is matched against, and the shortest prefix taken for an id.
SCAN: Final = 500
PREFIX: Final = 6


@beartype
class Bridge:
    """Starts, supervises, cancels and lists tasks across coders; recovers what a restart cut short."""

    __slots__ = ("_coders", "_gate", "_group", "_ledger", "_notifiers", "_profiles", "_projects", "_runs", "_stack")

    def __init__(
        self,
        *,
        coders: Mapping[CoderKind, CoderPort],
        notifiers: Mapping[str, NotifierPort],
        ledger: StorePort,
        profiles: Mapping[str, Profile],
        projects: ProjectIndex,
        limit: int,
    ) -> None:
        self._coders = coders
        self._projects = projects
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
        """A task by its id, or a unique head or tail of it: ids are uuid7, so tasks born in the same minute share
        their head and a chat shows the random tail."""
        match await self._ledger.get(KEY + (ref := task.strip())):
            case None if len(ref) >= PREFIX:
                hits = [key async for key in self._ledger.keys(KEY) if key.startswith(KEY + ref) or key.endswith(ref)]
                match hits:
                    case [one]:
                        return await self._common_load(one.removeprefix(KEY))
                    case []:
                        raise UnknownTaskError(task)
                    case many:
                        raise AmbiguousTaskError(task, tuple(key.removeprefix(KEY) for key in many))
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

    @staticmethod
    async def _common_session(port: CoderPort, session: str) -> CoderSession:
        """A session by what a caller copies reliably: its id, a unique id prefix, the first block of an id
        mangled in the copy, or its exact title."""
        match await port.session(ref := session.strip()):
            case CoderSession() as found:
                return found
        head, key = ref.split("-")[0], ref.casefold()
        rows = await port.sessions("", SCAN)
        hits = [
            row
            for row in rows
            if (len(ref) >= PREFIX and row.session.startswith(ref))
            or (len(head) >= PREFIX and row.session.startswith(head))
            or row.title.casefold() == key
        ]
        match hits:
            case [one]:
                return one
            case []:
                raise UnknownSessionError(session)
            case many:
                raise AmbiguousSessionError(session, tuple(row.session for row in many))

    async def _common_project(self, project: str) -> str:
        """A project name or path as its directory — resolved off the loop, it touches the filesystem."""
        return await anyio.to_thread.run_sync(self._projects.resolve, project)

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
        order = msgspec.structs.replace(order, cwd=await self._common_project(order.cwd))
        profile = self._start_profile(order)
        coder = self._common_coder(profile.coder)
        resumed = (await self._common_session(coder, order.session)).session if order.session else ""
        order = msgspec.structs.replace(order, session=resumed)
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

    async def find(
        self, project: str = "", text: str = "", limit: int = 10, coder: CoderKind = CoderKind.CLAUDE
    ) -> list[CoderSession]:
        """Recorded sessions, newest first: of one project (or all), whose title, branch or tag holds `text`."""
        cwd = await self._common_project(project) if project else ""
        needle = text.casefold()
        rows = await self._common_coder(coder).sessions(cwd, limit if not needle else 500)
        hits = (row for row in rows if needle in f"{row.title} {row.branch} {row.tag}".casefold())
        return [row for row, _ in zip(hits, range(limit), strict=False)]

    async def read(self, session: str, last: int = 6, coder: CoderKind = CoderKind.CLAUDE) -> SessionRead:
        """A session and its last turns — what it was about and where it stopped."""
        port = self._common_coder(coder)
        found = await self._common_session(port, session)
        return SessionRead(session=found, turns=tuple(await port.turns(found.session, last)))

    async def update(
        self, session: str, title: str | None = None, tag: str | None = None, coder: CoderKind = CoderKind.CLAUDE
    ) -> CoderSession:
        """The session after renaming and/or tagging it."""
        port = self._common_coder(coder)
        found = await self._common_session(port, session)
        await port.update(found.session, title, tag)
        return await self._common_session(port, found.session)

    async def catalog(self, project: str = "", coder: CoderKind = CoderKind.CLAUDE) -> CoderCatalog:
        """The commands, skills and agents the coder offers in a project."""
        return await self._common_coder(coder).catalog(await self._common_project(project))
