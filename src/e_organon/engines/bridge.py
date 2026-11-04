"""engines/bridge: the in-between — orders in, runs supervised, results recorded.

Every run lives in one TaskGroup, bounded by a semaphore; every transition is written to the ledger before anyone can
read it. A task is an immutable value and its lifecycle a transition table, never a flag: `running → done | failed |
cancelled`, and a terminal state goes nowhere. Ids are uuid7 — time-ordered, so the ledger's key order is the order
tasks were born in. The engine knows ports only: which coder and which store sit behind them is the composition root's
business, and it is an async context manager because it owns the group the runs live in."""

import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Self
from uuid import uuid7

import anyio
import msgspec

from e_organon.infra.errors import EngineError
from e_organon.infra.logger import logger
from e_organon.infra.struct import CheckedStruct
from e_organon.ports.coder import (
    CoderCatalog,
    CoderKind,
    CoderPeer,
    CoderPort,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    Profile,
    SessionRead,
    StartedEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from e_organon.ops.projects import NamedProjects
    from e_organon.ports.store import StorePort

### the ledger lives in the app's one store, so its keys carry their own namespace.
KEY: Final[str] = "tekton:task:"
INTERRUPTED: Final[str] = "interrupted: the bridge restarted while the task ran; resume its session"
SILENT: Final[str] = "the coder ended without a result"
### the sessions a prefix or a title is matched against, and the shortest prefix taken for an id.
SCAN: Final[int] = 500
PREFIX: Final[int] = 6


##### ERRORS #####
class BridgeError(EngineError):
    """Every refusal of the bridge: the edge turns it into a tool's error, never a crash."""


class UnknownTaskError(BridgeError):
    """No task carries this id."""

    def __init__(self, task: str) -> None:
        super().__init__(f"unknown task {task!r}")
        self.task = task


class AmbiguousTaskError(BridgeError):
    """A task prefix that matches more than one task: the caller must pass a longer one."""

    def __init__(self, task: str, matches: tuple[str, ...]) -> None:
        super().__init__(f"{task!r} matches several tasks: {', '.join(matches)}; pass a longer prefix")
        self.task = task


class UnknownSessionError(BridgeError):
    """No project of the coder holds a session with this id."""

    def __init__(self, session: str) -> None:
        super().__init__(f"unknown session {session!r}; tekton/find lists them")
        self.session = session


class AmbiguousSessionError(BridgeError):
    """A prefix or title that matches more than one session: the caller must pass a longer one."""

    def __init__(self, session: str, matches: tuple[str, ...]) -> None:
        super().__init__(f"{session!r} matches several sessions: {', '.join(matches)}; pass one of these ids")
        self.session = session


class UnknownProfileError(BridgeError):
    """The caller named a profile the book does not declare."""

    def __init__(self, profile: str, known: tuple[str, ...]) -> None:
        super().__init__(f"unknown profile {profile!r}; declared: {', '.join(known) or 'none'}")
        self.profile = profile


class UnknownCoderError(BridgeError):
    """A profile points at a coder no driver serves."""

    def __init__(self, coder: str) -> None:
        super().__init__(f"no coder serves {coder!r}")
        self.coder = coder


class RootDeniedError(BridgeError):
    """The working directory lies outside every root the profile allows."""

    def __init__(self, cwd: str, profile: str) -> None:
        super().__init__(f"cwd {cwd!r} is outside the roots of profile {profile!r}")
        self.cwd = cwd


class TaskStateError(BridgeError):
    """A transition the task lifecycle does not allow."""

    def __init__(self, task: str, source: str, target: str) -> None:
        super().__init__(f"task {task!r} cannot move {source} → {target}")
        self.task = task


##### VALUES #####
class TaskState(StrEnum):
    """Where a task is in its life."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS: Final[Mapping[TaskState, frozenset[TaskState]]] = MappingProxyType(
    {
        TaskState.RUNNING: frozenset({TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}),
        TaskState.DONE: frozenset(),
        TaskState.FAILED: frozenset(),
        TaskState.CANCELLED: frozenset(),
    }
)


class TaskOrder(CheckedStruct, frozen=True, kw_only=True):
    """What a caller asks for: a prompt run under a profile in a directory, optionally on an existing session."""

    prompt: str
    profile: str
    cwd: str
    session: str = ""
    fork: bool = False


class Task(CheckedStruct, frozen=True, kw_only=True):
    """One run on one coder: the order it came from, the session it lives in, and how it ended."""

    id: str
    coder: CoderKind
    profile: str
    prompt: str
    cwd: str
    state: TaskState = TaskState.RUNNING
    session: str = ""
    parent: str = ""
    fork: bool = False
    result: str = ""
    error: str = ""
    cost: float = 0.0
    turns: int = 0
    created: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))
    updated: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))

    @property
    def terminal(self) -> bool:
        return not TRANSITIONS[self.state]

    def move(self, state: TaskState, **changes: object) -> Self:
        """The same task in `state`, with `changes` applied; an illegal transition raises."""
        match state in TRANSITIONS[self.state]:
            case False:
                raise TaskStateError(self.id, self.state, state)
        return msgspec.structs.replace(self, state=state, updated=datetime.now(UTC), **changes)

    def bind(self, session: str) -> Self:
        """The same running task, now knowing the coder session it lives in."""
        return msgspec.structs.replace(self, session=session, updated=datetime.now(UTC))

    @classmethod
    def open(cls, order: TaskOrder, coder: CoderKind) -> Self:
        """A new running task for an order, its id time-ordered."""
        return cls(
            id=str(uuid7()),
            coder=coder,
            profile=order.profile,
            prompt=order.prompt,
            cwd=order.cwd,
            parent=order.session,
            fork=order.fork,
        )


##### ENGINE #####
class BridgeEngine:
    """Starts, supervises, cancels and lists tasks across coders; recovers what a restart cut short."""

    __slots__ = ("_coders", "_gate", "_group", "_ledger", "_profiles", "_projects", "_runs", "_stack")

    def __init__(
        self,
        *,
        coders: Mapping[CoderKind, CoderPort],
        ledger: StorePort,
        profiles: Mapping[str, Profile],
        projects: NamedProjects,
        limit: int,
    ) -> None:
        self._coders = coders
        self._projects = projects
        self._ledger = ledger
        self._profiles = profiles
        self._gate = asyncio.Semaphore(limit)
        self._runs: dict[str, asyncio.Task[None]] = {}
        self._stack = AsyncExitStack()
        self._group: asyncio.TaskGroup | None = None

    ##### PRIVATE #####

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
                msg = "BridgeEngine is not entered: the lifespan opens it, tools never do"
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
                await self._start_drive(task, coder, spec)
        except asyncio.CancelledError:
            ### the ledger holds what the drive learnt (its session): the local value is the one it started with; a run
            ### cancelled at the very moment it finished has already left its terminal state there.
            current = await self._common_load(task.id)
            _ = current.terminal or await self._common_save(current.move(TaskState.CANCELLED))
            raise
        except Exception as exc:  # noqa: BLE001 — the run boundary: a coder failure is the task's, not the bridge's
            logger.warning("task failed", task=task.id, error=repr(exc))
            await self._common_save((await self._common_load(task.id)).move(TaskState.FAILED, error=repr(exc)))

    async def _start_drive(self, task: Task, coder: CoderPort, spec: CoderSpec) -> Task:
        async for event in coder.run(spec):
            match event:
                case StartedEvent(session=session):
                    task = await self._common_save(task.bind(session))
                case finished:
                    return await self._start_finish(task, finished)
        return await self._common_save(task.move(TaskState.FAILED, error=SILENT))

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
        logger.info("bridge open", recovered=await self._common_recover(), profiles=len(self._profiles))
        return self

    async def __aexit__(self, *exc: object) -> None:
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
        logger.info("task started", task=task.id, profile=profile.name, coder=profile.coder, resume=bool(order.session))
        return task

    async def status(self, task: str, wait: float = 0.0) -> Task:
        """The task now — or, with `wait` seconds, once it ends or the wait runs out, whichever comes first."""
        match self._runs.get(task):
            case asyncio.Task() as run if wait > 0:
                await asyncio.wait({run}, timeout=wait)
        return await self._common_load(task)

    async def watch(self, task: str, wait: float, tick: float) -> AsyncIterator[Task]:
        """The task at each `tick` of a `wait` — the last one is it ended, or the wait spent. Recursion depth is
        `wait / tick`: the caller bounds the wait."""
        current = await self.status(task, min(tick, wait))
        yield current
        match current.terminal or wait <= tick:
            case False:
                async for later in self.watch(task, wait - tick, tick):
                    yield later

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
        rows = await self._common_coder(coder).sessions(cwd, limit if not needle else SCAN)
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
