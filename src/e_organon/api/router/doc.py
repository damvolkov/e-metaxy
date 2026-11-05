"""api.router.doc: the doc/ section — one route per canonical tool, each streamed, batched or queued by the request.

A handler only hands the request and its arguments to the tool's workflow on the sealed graph
(`graph.services.doc.<tool>`); `api.stream` decides the reading. The MCP twins (`mcp/tools/doc`) are these handlers."""

from typing import Any, Final

from litestar import Request, post
from litestar.di import NamedDependency, Provide
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody

from e_organon.api.deps import DepKey, graph
from e_organon.api.security import SECURITY
from e_organon.api.stream import answer
from e_organon.infra.auth.guard import OPT
from e_organon.infra.auth.models import Access
from e_organon.infra.state import State
from e_organon.models.doc import (
    ConvertIn,
    FillIn,
    InspectIn,
    MergeIn,
    OcrIn,
    RenderIn,
    SignatureIn,
    SignIn,
    SplitIn,
    StampIn,
)

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}


##### HANDLERS #####
async def convert(data: JSONBody[ConvertIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/convert: a document as Markdown."""
    return await answer(request, graph.services.doc.convert, data)


async def inspect(data: JSONBody[InspectIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/inspect: a PDF's pages, metadata and form fields."""
    return await answer(request, graph.services.doc.inspect, data)


async def merge(data: JSONBody[MergeIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/merge: PDFs joined into one."""
    return await answer(request, graph.services.doc.merge, data)


async def split(data: JSONBody[SplitIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/split: page ranges as their own PDFs."""
    return await answer(request, graph.services.doc.split, data)


async def fill(data: JSONBody[FillIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/fill: a PDF form's fields written by name."""
    return await answer(request, graph.services.doc.fill, data)


async def render(data: JSONBody[RenderIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/render: PDF pages as PNG."""
    return await answer(request, graph.services.doc.render, data)


async def stamp(data: JSONBody[StampIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/stamp: an image or a text drawn on a PDF page."""
    return await answer(request, graph.services.doc.stamp, data)


async def signature(data: JSONBody[SignatureIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/signature: a photographed signature placed on a PDF."""
    return await answer(request, graph.services.doc.signature, data)


async def ocr(data: JSONBody[OcrIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/ocr: the words of a scan, each with its box."""
    return await answer(request, graph.services.doc.ocr, data)


async def sign(data: JSONBody[SignIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/sign: a PDF signed in PAdES with the deployment's key."""
    return await answer(request, graph.services.doc.sign, data)


##### ROUTES #####
def routes(*handlers: Any) -> tuple[HTTPRouteHandler, ...]:
    """One `POST /doc/<name>` route for each handler."""
    return tuple(
        post(
            f"/doc/{handler.__name__}",
            name=f"doc.{handler.__name__}",
            status_code=200,
            tags=["doc"],
            opt=OPT[Access.USER],
            security=SECURITY,
            dependencies=TOOL_DEPS,
        )(handler)
        for handler in handlers
    )


### the tools every deployment serves; `OCR` only where its engine is on (OCR_ENABLED), `SIGN` where a key is set (SIGN_P12).
ROUTES: tuple[HTTPRouteHandler, ...] = routes(convert, inspect, merge, split, fill, render, stamp, signature)
OCR: tuple[HTTPRouteHandler, ...] = routes(ocr)
SIGN: tuple[HTTPRouteHandler, ...] = routes(sign)
