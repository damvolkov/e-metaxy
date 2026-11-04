"""ports/coder: an engineer harness (Claude Code, OpenCode) — a run is a stream of events, its live sessions are peers.

A run is one `CoderSpec` played as events: `StartedEvent` the moment the coder knows its session, `FinishedEvent` once,
at the end; the coder never knows who listens. Recorded sessions are read, renamed and tagged by id; the catalog says
what the harness offers in a project without spending a model turn. A `Profile` is the nomos of a caller: what it may
make a coder do, by name — a caller picks a profile and never passes a flag."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

import msgspec

from e_organon.infra.struct import CheckedStruct
from e_organon.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping


##### PROFILE #####
class CoderKind(StrEnum):
    """The engineer harnesses that can be driven."""

    CLAUDE = "claude"
    OPENCODE = "opencode"


class ProfileMode(StrEnum):
    """How the coder treats a tool outside `allow`: ask nobody and deny, accept edits, plan only, decide,
    or approve everything — `bypassPermissions`, the mode of working directly; deny rules and hooks still hold."""

    DEFAULT = "default"
    DONT_ASK = "dontAsk"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    AUTO = "auto"
    BYPASS = "bypassPermissions"


class Profile(CheckedStruct, frozen=True, kw_only=True):
    """One named policy: coder, permission mode, tools, the roots a task may run under, and its limits. Every mode is a
    member, so the full-permission one exists only when a book declares it by name and a caller chooses it."""

    name: str = ""
    coder: CoderKind = CoderKind.CLAUDE
    mode: ProfileMode = ProfileMode.DONT_ASK
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    roots: tuple[str, ...] = ()
    turns: int | None = None
    budget: float | None = None
    model: str | None = None
    note: str = ""

    def admits(self, cwd: Path) -> bool:
        """Whether `cwd` lives under one of the roots; a profile without roots admits nothing."""
        target = cwd.expanduser().resolve()
        return any(target.is_relative_to(Path(root).expanduser().resolve()) for root in self.roots)

    @classmethod
    def book(cls, raw: bytes) -> Mapping[str, Profile]:
        """Every profile of a YAML book, keyed by name and named after its key — frozen."""
        decoded = msgspec.yaml.decode(raw, type=dict[str, dict[str, object]])
        return MappingProxyType({name: cls.convert({**fields, "name": name}, cls) for name, fields in decoded.items()})


##### RUN #####
class CoderSpec(CheckedStruct, frozen=True, kw_only=True):
    """One run as a coder sees it: the prompt, where, under which profile, on which session."""

    prompt: str
    cwd: str
    profile: Profile
    session: str = ""
    fork: bool = False


class StartedEvent(CheckedStruct, frozen=True, kw_only=True, tag="started"):
    """The coder knows its session."""

    session: str


class FinishedEvent(CheckedStruct, frozen=True, kw_only=True, tag="finished"):
    """The run ended: its result, or why it failed, and what it cost."""

    session: str = ""
    result: str = ""
    failed: bool = False
    error: str = ""
    cost: float = 0.0
    turns: int = 0


type CoderEvent = StartedEvent | FinishedEvent


##### PEERS #####
class PeerStatus(StrEnum):
    """What a live session is doing."""

    IDLE = "idle"
    BUSY = "busy"
    UNKNOWN = "unknown"


class CoderPeer(CheckedStruct, frozen=True, kw_only=True):
    """A live session of a coder, addressable by name."""

    name: str
    ref: str = ""
    kind: str = ""
    status: PeerStatus = PeerStatus.UNKNOWN


class CoderReceipt(CheckedStruct, frozen=True, kw_only=True):
    """Whether a message reached a peer's inbox — delivery, not reading."""

    peer: str
    delivered: bool
    detail: str = ""


##### SESSIONS #####
class CoderSession(CheckedStruct, frozen=True, kw_only=True):
    """A recorded session of a coder — closed or live, addressable by id to read, rename or resume."""

    session: str
    title: str = ""
    cwd: str = ""
    branch: str = ""
    tag: str = ""
    modified: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))


class TurnRole(StrEnum):
    """Who spoke in a turn: the person, the coder, or a tool the coder called."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class SessionTurn(CheckedStruct, frozen=True, kw_only=True):
    """One readable step of a session: what the user asked, what the coder answered, which tool it called."""

    role: TurnRole
    text: str


class SessionRead(CheckedStruct, frozen=True, kw_only=True):
    """A session and its last turns, oldest first — enough to pick it up where it stopped."""

    session: CoderSession
    turns: tuple[SessionTurn, ...] = ()


##### CATALOG #####
class CatalogEntry(CheckedStruct, frozen=True, kw_only=True):
    """A command, skill or agent the coder offers, with what it is for."""

    name: str
    description: str = ""
    hint: str = ""


class CoderCatalog(CheckedStruct, frozen=True, kw_only=True):
    """What the coder can do in one project: its slash commands and skills, and its agents."""

    cwd: str
    commands: tuple[CatalogEntry, ...] = ()
    agents: tuple[CatalogEntry, ...] = ()


##### PORT #####
@runtime_checkable
class CoderPort(Provider, Protocol):
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
