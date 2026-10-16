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


class CoderSession(CheckedStruct, frozen=True, kw_only=True):
    """A recorded session of a coder — closed or live, addressable by id for a resume."""

    session: str
    title: str = ""
    cwd: str = ""
    modified: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))
