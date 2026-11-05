"""api.stream: one route, three readings — the workflow's events as they happen, its answer at the end, or a job.

`answer` reads the request. `Prefer: respond-async` (RFC 7240) gets the tool run in the background: `202` with the job and
`Location: /jobs/{id}` — a tool that is no job (the bridge's) ignores the preference, as the RFC lets a server. Else
`Accept: text/event-stream` gets every event as a server-sent event, named by its kind (`step`, `done`, `failed`); anything
else gets the batch answer — the result as JSON, or the `Failed` as 422 `kind: reason`. A tool route is `POST` either way,
so a client batches, streams or queues with the same call."""

from collections.abc import AsyncIterator
from typing import Any, Final

import msgspec
from litestar import Request, Response
from litestar.exceptions import HTTPException
from litestar.response.sse import ServerSentEvent, ServerSentEventMessage
from litestar.status_codes import HTTP_202_ACCEPTED

from e_organon.api.state import AppState
from e_organon.models.error import FlowError
from e_organon.models.flow import Event
from e_organon.models.job import AcceptedJob
from e_organon.services.flow import ToolFlow

STREAM: Final[str] = "text/event-stream"
BACKGROUND: Final[str] = "respond-async"
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
        ### `kind: reason` in the detail: `extra` is the shape of validation errors, which the MCP bridge reads as such.
        raise HTTPException(status_code=REFUSED, detail=f"{exc.failed.kind}: {exc.failed.reason}") from exc


def _answer_preferred(request: Request[Any, Any, Any]) -> bool:
    """Whether `Prefer` holds the token `respond-async`: preferences are comma-separated, each a token, `=` and `;` after."""
    preferences = ",".join(request.headers.getall("prefer", []))
    return BACKGROUND in {part.split(";")[0].split("=")[0].strip().lower() for part in preferences.split(",")}


async def _answer_job[I](request: Request[Any, Any, Any], tool: ToolFlow[I, Any], data: I) -> Response[AcceptedJob]:
    accepted = await AppState.of(request.app).system.services.jobs.submit(tool, data)
    return Response(
        accepted,
        status_code=HTTP_202_ACCEPTED,
        headers={"Location": f"/jobs/{accepted.job}", "Preference-Applied": BACKGROUND},
    )


def follow(events: AsyncIterator[Event]) -> ServerSentEvent:
    """The events as server-sent events, each named by its kind."""
    return ServerSentEvent(_answer_events(events))


async def answer[I](request: Request[Any, Any, Any], tool: ToolFlow[I, Any], data: I) -> Any:
    """The tool queued as a job when `Prefer: respond-async` and it is one, else streamed when the client accepts
    `text/event-stream`, its answer otherwise."""
    queued = _answer_preferred(request) and AppState.of(request.app).system.services.jobs.accepts(tool)
    match (queued, STREAM in request.headers.get("accept", "")):
        case (True, _):
            return await _answer_job(request, tool, data)
        case (False, True):
            return follow(tool.events(data))
        case _:
            return await _answer_batch(tool, data)
