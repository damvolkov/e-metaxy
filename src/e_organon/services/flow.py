"""e_organon.services.flow: the shape of every canonical tool — a workflow that streams its steps and ends in an answer.

A tool subclasses `ToolFlow` and writes `_events_run`, an async generator of `Step`s that ends in `Done`. `events` is
that stream made total: whatever the workflow raises becomes its last event, `Failed`, so a stream never breaks
mid-way. `run` is the batch reading of the same stream — the answer, or `FlowError` with the very `Failed` a stream
would have sent. REST streams or batches per request; the MCP twin batches."""

from types import get_original_bases
from typing import TYPE_CHECKING, get_args, get_origin

from e_organon.infra.logger import logger
from e_organon.models.error import FlowError
from e_organon.models.flow import Done, Event, Failed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


##### FLOW #####
class ToolFlow[I, O]:
    """A canonical tool: `_events_run` is its workflow, `events` streams it, `run` answers it."""

    ##### PRIVATE #####

    def _events_run(self, data: I) -> AsyncIterator[Event]:
        raise NotImplementedError

    ############################################################

    ##### PUBLIC #####

    @classmethod
    def arguments(cls) -> type[I]:
        """The input type the tool was declared over — `ToolFlow[ConvertIn, ConvertOut]` says `ConvertIn` —: what a job
        stored as builtins is decoded into."""
        return next(get_args(base)[0] for base in get_original_bases(cls) if get_origin(base) is ToolFlow)

    async def events(self, data: I) -> AsyncIterator[Event]:
        """Every event the workflow emits; a raise becomes the last one, `Failed`."""
        try:
            async for event in self._events_run(data):
                yield event
        except Exception as exc:  # noqa: BLE001 — the stream's boundary: a failure is an event, never a broken stream
            logger.warning("tool failed", tool=type(self).__name__, error=repr(exc))
            yield Failed(kind=type(exc).__name__, reason=str(exc))

    async def run(self, data: I) -> O:
        """The answer: the last event's result, or `FlowError` carrying the `Failed` a stream would end in."""
        stream = [event async for event in self.events(data)]
        match stream[-1] if stream else None:
            case Done(result=result):
                return result
            case Failed() as failed:
                raise FlowError(failed)
            case _:
                raise FlowError(Failed(kind="EmptyFlow", reason=f"{type(self).__name__} ended without an answer"))
