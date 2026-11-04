"""api.stream: one route, two readings — the workflow's events as they happen, or its answer at the end.

`answer` reads the request's `Accept`: `text/event-stream` gets every event as a server-sent event, named by its kind
(`step`, `done`, `failed`); anything else gets the batch answer — the result as JSON, or the `Failed` with 422. A tool
route is `POST` either way, so a client batches with the same call it would stream."""

from collections.abc import AsyncIterator
from typing import Any, Final

import msgspec
from litestar import Request
from litestar.exceptions import HTTPException
from litestar.response.sse import ServerSentEvent, ServerSentEventMessage

from e_organon.models.error import FlowError
from e_organon.models.flow import Event
from e_organon.services.flow import ToolFlow

STREAM: Final[str] = "text/event-stream"
REFUSED: Final[int] = 422


##### STREAM #####
async def _answer_events(events: AsyncIterator[Event]) -> AsyncIterator[ServerSentEventMessage]:
    async for event in events:
        yield ServerSentEventMessage(
            event=str(type(event).__struct_config__.tag), data=msgspec.json.encode(event).decode()
        )


async def _answer_batch[I](tool: ToolFlow[I, Any], data: I) -> Any:
    try:
        return await tool.run(data)
    except FlowError as exc:
        raise HTTPException(status_code=REFUSED, detail=exc.failed.reason, extra={"kind": exc.failed.kind}) from exc


async def answer[I](request: Request[Any, Any, Any], tool: ToolFlow[I, Any], data: I) -> Any:
    """The workflow streamed when the client accepts `text/event-stream`, its answer otherwise."""
    streamed = STREAM in request.headers.get("accept", "")
    return ServerSentEvent(_answer_events(tool.events(data))) if streamed else await _answer_batch(tool, data)
