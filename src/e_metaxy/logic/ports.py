"""e_metaxy.logic.ports: what the bridge asks of the world — structural contracts, never a concretion.

`CoderPort` is an engineer harness (Claude Code, OpenCode): it runs a spec as a stream of events and reaches
the harness's live sessions. `NotifierPort` is a polymath harness to call back when a task ends."""

from collections.abc import AsyncIterator
from typing import ClassVar, Protocol, runtime_checkable

from e_metaxy.models.coder import CoderEvent, CoderPeer, CoderReceipt, CoderSpec
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import Task


@runtime_checkable
class CoderPort(Protocol):
    """An engineer harness: one run is an event stream; its live sessions are peers."""

    kind: ClassVar[CoderKind]

    def run(self, spec: CoderSpec) -> AsyncIterator[CoderEvent]:
        """`StartedEvent` once the session is known, `FinishedEvent` once at the end; cancellation interrupts."""
        ...

    async def peers(self) -> list[CoderPeer]: ...

    async def send(self, peer: str, text: str) -> CoderReceipt: ...


@runtime_checkable
class NotifierPort(Protocol):
    """A caller to tell when one of its tasks ends; a failed call is logged by the adapter, never raised."""

    name: ClassVar[str]

    async def notify(self, task: Task) -> None: ...
