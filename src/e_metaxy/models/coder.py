"""e_metaxy.models.coder: what crosses the Coder port — the spec in, events, peers and history out.

A run is a stream of events: `StartedEvent` the moment the coder knows its session, `FinishedEvent` once,
at the end. The bridge reacts to each; the coder never knows who listens."""

from datetime import UTC, datetime
from enum import StrEnum

import msgspec

from e_metaxy.core.struct import CheckedStruct
from e_metaxy.models.profile import Profile


##### RUN #####
class CoderSpec(CheckedStruct, frozen=True, kw_only=True):
    """One run as a coder sees it: the prompt, where, under which profile, on which session."""

    prompt: str
    cwd: str
    profile: Profile
    session: str = ""
    fork: bool = False


class StartedEvent(CheckedStruct, frozen=True, kw_only=True, tag="started"):
    session: str


class FinishedEvent(CheckedStruct, frozen=True, kw_only=True, tag="finished"):
    session: str = ""
    result: str = ""
    failed: bool = False
    error: str = ""
    cost: float = 0.0
    turns: int = 0


type CoderEvent = StartedEvent | FinishedEvent


##### PEERS #####
class PeerStatus(StrEnum):
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
