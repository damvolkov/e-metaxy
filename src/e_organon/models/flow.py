"""e_organon.models.flow: what a canonical tool tells while it runs — each step it enters, then its answer or why not.

Every tool is a workflow and every workflow is a stream of these events, so every route streams: a client that asks
for `text/event-stream` reads them as they happen, any other reads the last one — the same route, streamed or batched.
"""

from typing import Any

import msgspec


##### EVENTS #####
class Step(msgspec.Struct, frozen=True, kw_only=True, tag="step"):
    """The workflow entered `name`, step `index` of `total`."""

    name: str
    index: int
    total: int


class Done(msgspec.Struct, frozen=True, kw_only=True, tag="done"):
    """The workflow's answer: the tool's output, the last event."""

    result: Any


class Failed(msgspec.Struct, frozen=True, kw_only=True, tag="failed"):
    """Why the workflow stopped: `kind` is the error's class, `reason` its message — the last event."""

    kind: str
    reason: str


type Event = Step | Done | Failed
