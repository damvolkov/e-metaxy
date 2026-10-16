"""e_metaxy.logic.ports: what the bridge asks of the world — structural contracts, never a concretion.

`CoderPort` is an engineer harness (Claude Code, OpenCode): it runs a spec as a stream of events, reaches
the harness's live sessions and lists its recorded ones. `NotifierPort` is a polymath harness to call back
when a task ends. `OwnerPort` is who may approve a client on the consent page."""

from collections.abc import AsyncIterator
from typing import ClassVar, Protocol, runtime_checkable

from e_metaxy.models.coder import (
    CoderCatalog,
    CoderEvent,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    SessionTurn,
)
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

    async def sessions(self, cwd: str, limit: int) -> list[CoderSession]:
        """The coder's recorded sessions, newest first; `cwd` empty means every project."""
        ...

    async def session(self, session: str) -> CoderSession | None:
        """One recorded session by id, wherever it lives; None when no project holds it."""
        ...

    async def turns(self, session: str, last: int) -> list[SessionTurn]:
        """The session's last `last` readable turns, oldest first."""
        ...

    async def update(self, session: str, title: str | None, tag: str | None) -> None:
        """Rename and/or tag a session; None leaves that field as it is, an empty tag clears it."""
        ...

    async def catalog(self, cwd: str) -> CoderCatalog:
        """The commands, skills and agents the coder offers in `cwd` — read without a model turn."""
        ...


@runtime_checkable
class NotifierPort(Protocol):
    """A caller to tell when one of its tasks ends; a failed call is logged by the adapter, never raised."""

    name: ClassVar[str]

    async def notify(self, task: Task) -> None: ...


@runtime_checkable
class OwnerPort(Protocol):
    """The owner of the bridge: whether a secret presented on the consent page proves it is them."""

    async def admits(self, secret: str) -> bool:
        """True only for the owner's secret; a wrong one is False, never an exception."""
        ...
