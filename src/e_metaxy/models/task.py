"""e_metaxy.models.task: a task is an immutable value; its lifecycle is a transition table, never a flag.

`running → done | failed | cancelled`, and a terminal state goes nowhere. Ids are uuid7: time-ordered, so the
ledger's key order is the order tasks were born in."""

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final, Self
from uuid import uuid7

import msgspec

from e_metaxy.core.struct import CheckedStruct
from e_metaxy.models.error import TaskStateError
from e_metaxy.models.profile import CoderKind


##### ENUMS #####
class TaskState(StrEnum):
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


##### MODELS #####
class TaskOrder(CheckedStruct, frozen=True, kw_only=True):
    """What a caller asks for: a prompt run under a profile in a directory, optionally on an existing session."""

    prompt: str
    profile: str
    cwd: str
    session: str = ""
    fork: bool = False
    caller: str = ""

    def expanded(self) -> Self:
        """The order with `~` in its cwd made the home: the coder needs the directory itself, the ledger what ran."""
        return msgspec.structs.replace(self, cwd=str(Path(self.cwd).expanduser()))


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
    caller: str = ""
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
            caller=order.caller,
        )
