"""e_metaxy.models.eng: an `eng` order as a value — one variant per verb of the shared grammar.

Every front (a chat agent, a channel's Claude, a future OpenCode channel) passes the user's words untouched;
the grammar turns them into one of these, and only then does anything run. `ref` names a session the way a
person copies it: its id, its first characters, or its exact title."""

from e_metaxy.core.struct import CheckedStruct


##### VARIANTS #####
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
