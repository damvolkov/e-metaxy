"""e_organon.models.tekton: what the tekton/ tools take and give — the bridge to the engineer harnesses, by name.

A caller names a project (a short name or a path) and a profile, never a flag; a task is answered as `TaskOut`, a
session or a peer as the coder port's own values. An `eng` order is the shared grammar's value: one variant per verb,
built from the user's words untouched, and only then does anything run."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self

import msgspec

from e_organon.infra.struct import CheckedStruct
from e_organon.ports.coder import CoderKind, CoderPeer, CoderSession

LIMIT = Annotated[int, msgspec.Meta(ge=1, le=100)]
LAST = Annotated[int, msgspec.Meta(ge=0, le=100)]


##### SHARED #####
class TaskOut(msgspec.Struct, frozen=True, kw_only=True):
    """One run on one coder: the order it came from, the `session` it lives in (continue it with `tekton/start`), its
    `state` (running, done, failed, cancelled) and how it ended — `result`, `error`, `cost` and `turns`."""

    id: str
    coder: CoderKind
    profile: str
    prompt: str
    cwd: str
    state: str
    session: str = ""
    parent: str = ""
    fork: bool = False
    result: str = ""
    error: str = ""
    cost: float = 0.0
    turns: int = 0
    created: datetime
    updated: datetime

    @classmethod
    def of(cls, task: object) -> Self:
        """The wire shape of a bridge task, read by attribute: the model never imports the engine that makes it."""
        return msgspec.convert(task, cls, from_attributes=True)


class TasksOut(msgspec.Struct, frozen=True, kw_only=True):
    """Tasks, newest first."""

    tasks: list[TaskOut]


##### ENG #####
class EngIn(msgspec.Struct, frozen=True, kw_only=True):
    """`text`: the user's `eng` message as typed; `project`: the project the conversation is about, for an order that
    names none; `profile`: what a new run may do."""

    text: str
    project: str = ""
    profile: str = "code"


class EngOut(msgspec.Struct, frozen=True, kw_only=True):
    """`verb`: which verb of the grammar ran; `result`: what it answered — a task, a session, sessions or tasks."""

    verb: str
    result: Any


class EngNew(CheckedStruct, frozen=True, kw_only=True, tag="new"):
    """`eng [project:] <order>` — a fresh session; without a project, the one the caller inferred."""

    project: str
    prompt: str
    named: bool = False


class EngResume(CheckedStruct, frozen=True, kw_only=True, tag="resume"):
    """`eng @ref: <order>` continues the session; `eng @ref+: <order>` branches it."""

    ref: str
    prompt: str
    fork: bool = False


class EngRead(CheckedStruct, frozen=True, kw_only=True, tag="read"):
    """`eng @ref?` — where the session stopped."""

    ref: str


class EngRename(CheckedStruct, frozen=True, kw_only=True, tag="rename"):
    """`eng @ref = <title>` — the session's new title."""

    ref: str
    title: str


class EngList(CheckedStruct, frozen=True, kw_only=True, tag="list"):
    """`eng ls [project]` — recorded sessions, newest first."""

    project: str = ""


class EngStatus(CheckedStruct, frozen=True, kw_only=True, tag="status"):
    """`eng ps` — the newest tasks."""


class EngStop(CheckedStruct, frozen=True, kw_only=True, tag="stop"):
    """`eng stop <task>` — interrupt a running task."""

    task: str


type EngOrder = EngNew | EngResume | EngRead | EngRename | EngList | EngStatus | EngStop


##### START #####
class StartIn(msgspec.Struct, frozen=True, kw_only=True):
    """`prompt`: plain words, or a command or skill (`/research vLLM`); `project`: a short name or a path; `profile`:
    what the run may do; `session`: continue that conversation (its id, its first characters or its exact title);
    `fork`: branch it instead."""

    prompt: str
    project: str
    profile: str = "code"
    session: str = ""
    fork: bool = False


##### STATUS #####
class StatusIn(msgspec.Struct, frozen=True, kw_only=True):
    """`task`: its id, or a unique head or tail of it; `wait`: seconds to hold for its end (at most 25)."""

    task: str
    wait: float = 0.0


##### TASKS #####
class TasksIn(msgspec.Struct, frozen=True, kw_only=True):
    """`state`: narrows to one state; `limit`: how many, newest first."""

    state: Literal["running", "done", "failed", "cancelled"] | None = None
    limit: LIMIT = 20


##### CANCEL #####
class CancelIn(msgspec.Struct, frozen=True, kw_only=True):
    """`task`: its id, or a unique head or tail of it."""

    task: str


##### CATALOG #####
class CatalogIn(msgspec.Struct, frozen=True, kw_only=True):
    """`project`: a short name or a path; empty is the workspace root."""

    project: str = ""


##### FIND #####
class FindIn(msgspec.Struct, frozen=True, kw_only=True):
    """`project`: narrows to one project; `text`: to titles, branches or tags that contain it; `limit`: how many."""

    project: str = ""
    text: str = ""
    limit: LIMIT = 10


class FindOut(msgspec.Struct, frozen=True, kw_only=True):
    """Recorded sessions, newest first."""

    sessions: list[CoderSession]


##### READ #####
class ReadIn(msgspec.Struct, frozen=True, kw_only=True):
    """`session`: its id, its first characters or its exact title; `last`: how many turns."""

    session: str
    last: LAST = 6


##### UPDATE #####
class UpdateIn(msgspec.Struct, frozen=True, kw_only=True):
    """`session`: its id, its first characters or its exact title; `title` and `tag`: what to set — an empty tag
    clears it, none leaves it."""

    session: str
    title: str | None = None
    tag: str | None = None


##### PEERS #####
class PeersIn(msgspec.Struct, frozen=True, kw_only=True):
    """Nothing: the sessions open in a terminal right now."""


class PeersOut(msgspec.Struct, frozen=True, kw_only=True):
    """The sessions open in a terminal: name, kind, idle or busy."""

    peers: list[CoderPeer]


##### SEND #####
class SendIn(msgspec.Struct, frozen=True, kw_only=True):
    """`peer`: an open session's name (see `tekton/peers`); `text`: what to deliver."""

    peer: str
    text: str
