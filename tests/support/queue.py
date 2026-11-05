"""tests/support/queue: the queue's database and a durable `QueuePort`, neither holding a database — the queue down by default, so the dispatch falls back to
memory as it does when the queue's database is unreachable; up, it records what the dispatch asks of it."""

from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Self

from e_organon.infra.background import BackgroundJob, BackgroundState
from e_organon.infra.errors import QueueError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from e_organon.infra.background import BackgroundHandler
    from e_organon.ports.database import Notify, QueryPort, Row


@dataclass(slots=True)
class FakeQueue:
    """A queue that is `up` or refuses on entry; `kinds` the kind to (queue, handler) it was asked to bind, `slots` what
    it was started with, `jobs_held` what it enqueued."""

    up: bool = False
    kinds: dict[str, tuple[str, BackgroundHandler]] = field(default_factory=dict)
    slots: dict[str, int] = field(default_factory=dict)
    held: list[BackgroundJob] = field(default_factory=list)

    spec: ClassVar[ProviderSpec] = ProviderSpec("fake-queue", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)

    async def __aenter__(self) -> Self:
        match self.up:
            case True:
                return self
            case False:
                msg = "the queue's database is down"
                raise QueueError(msg)

    async def __aexit__(self, *exc: object) -> None: ...

    async def health(self) -> bool:
        return self.up

    def register(self, kind: str, queue: str, handler: BackgroundHandler) -> None:
        self.kinds[kind] = (queue, handler)

    async def start(self, slots: Mapping[str, int]) -> None:
        self.slots = dict(slots)

    async def enqueue(self, kind: str, args: Mapping[str, Any], *, queue: str, attempts: int) -> BackgroundJob:
        job = BackgroundJob(
            id=str(len(self.held) + 1),
            kind=kind,
            queue=queue,
            state=BackgroundState.AVAILABLE,
            attempt=0,
            args=args,
            created=datetime.now(UTC),
        )
        self.held.append(job)
        return job

    async def job(self, job: str) -> BackgroundJob | None:
        return next((each for each in self.held if each.id == job), None)

    async def jobs(
        self, *, kind: str | None = None, state: BackgroundState | None = None, limit: int = 20
    ) -> list[BackgroundJob]:
        return [each for each in reversed(self.held) if kind in {None, each.kind} and state in {None, each.state}][
            :limit
        ]

    async def cancel(self, job: str) -> BackgroundJob | None:
        return await self.job(job)


class FakeQueueDatabase:
    """The queue's database where asyncpg would connect: opens, answers, holds nothing — a `DatabaseListenPort` whose
    statements and LISTEN are no-ops, for a durable queue that is the test's own (`FakeQueue`)."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "fake-queue-database", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP
    )

    def __init__(self, **_: object) -> None: ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None: ...

    async def health(self) -> bool:
        return True

    async def execute(self, query: str, params: Sequence[object] = ()) -> None: ...

    async def fetch(self, query: str, params: Sequence[object] = ()) -> list[Row]:
        return []

    async def row(self, query: str, params: Sequence[object] = ()) -> Row | None:
        return None

    async def many(self, query: str, params: Sequence[Sequence[object]]) -> None: ...

    async def script(self, statements: str) -> None: ...

    def transaction(self) -> AbstractAsyncContextManager[QueryPort]:
        return nullcontext(self)

    def connection(self) -> AbstractAsyncContextManager[QueryPort]:
        return nullcontext(self)

    async def listen(self, channel: str, callback: Notify) -> None: ...

    async def unlisten(self, channel: str, callback: Notify) -> None: ...
