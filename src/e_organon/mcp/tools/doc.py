"""e_organon.mcp.tools.doc: the doc/ section as tools — the twin of `api/router/doc`, whose very handlers they are.

The MCP engine asks for JSON, so a tool always answers in batch: the result, or the `Failed` reason as its error. Paths
are under the vault or the workspaces; a written file lands in the outbox, content-named, and is the next tool's input."""

from collections.abc import Callable
from typing import Any, Final

from litestar.handlers import HTTPRouteHandler

from e_organon.api.router import doc as router
from e_organon.infra.auth.models import Access
from e_organon.infra.mcp.models import MCPTool
from e_organon.mcp.refusals import REFUSALS

##### TOOLS — what a client is told #####
CONVERT: Final = MCPTool(
    name="doc_convert",
    title="Convert a document to Markdown",
    description=(
        "Any document (PDF, Office, HTML, images, EPUB…) under the vault or the workspaces, by `path`, read into "
        "Markdown: tables as tables, scans read, pages in order. No model reads it — the engines do. Returns "
        "`name` and `markdown`."
    ),
)
INSPECT: Final = MCPTool(
    name="doc_inspect",
    title="Inspect a PDF",
    description=(
        "A PDF by `path`: each page's size in points (origin bottom-left), its metadata and every form field — full "
        "name, kind, page, rectangle, value. Read this before doc_fill; it never returns the PDF's text."
    ),
)
MERGE: Final = MCPTool(
    name="doc_merge",
    title="Merge PDFs",
    description="Two or more PDFs by `paths`, joined in that order into one; `name` is its stem. Returns its `path`.",
    read_only=False,
)
SPLIT: Final = MCPTool(
    name="doc_split",
    title="Split a PDF",
    description=(
        "A PDF by `path`, cut into `ranges` — `[first, last]` page pairs counted from 0, both included — one PDF each. "
        "Returns their paths."
    ),
    read_only=False,
)
FILL: Final = MCPTool(
    name="doc_fill",
    title="Fill a PDF form",
    description=(
        "A PDF form by `path`, its fields set from `values` (full field name → value; a checkbox takes true/false), "
        "as doc_inspect names them; an unknown name refuses the fill. Returns the filled copy's `path`."
    ),
    read_only=False,
)
RENDER: Final = MCPTool(
    name="doc_render",
    title="Render PDF pages",
    description=(
        "A PDF by `path`, its `pages` (from 0; all when empty) drawn as PNG at `dpi` (36-600, default 110). "
        "Returns the images' paths."
    ),
    read_only=False,
)

STAMP: Final = MCPTool(
    name="doc_stamp",
    title="Stamp a PDF",
    description=(
        "An `image` (a PNG path, its transparency kept) or a `text` drawn on a PDF by `path`, `at` a form field, a text "
        "anchor or a box (PDF points, bottom-left origin). The image keeps its aspect ratio. Returns the copy's `path`."
    ),
    read_only=False,
)
SIGNATURE: Final = MCPTool(
    name="doc_signature",
    title="Sign a PDF with a photo",
    description=(
        "A photo of a handwritten signature (`photo`) cut out and placed on a PDF (`path`) `at` as doc_stamp's. Visual "
        "only, not a cryptographic signature; `lines` (default) drops printed lines — off if the signature has its own straight underline. Returns the copy's `path`."
    ),
    read_only=False,
)

COMPOSE: Final = MCPTool(
    name="doc_compose",
    title="Compose a PDF from a template",
    description=(
        "A PDF/A made from a typst `template` — a name (`invoice`, shipped; the deployment may keep others) or a path to a "
        ".typ file under the vault or the workspaces — and its `data` (JSON the template reads). The same input gives the "
        "same bytes. Returns the PDF's `path`."
    ),
    read_only=False,
)
REDACT: Final = MCPTool(
    name="doc_redact",
    title="Redact a PDF",
    description=(
        "A PDF by `path` with text and images removed for good, not covered: the `terms` (literal, case ignored; or "
        "regular expressions with `regex`) on `pages` (from 0, all when empty) and the `boxes` (`page`, `x`, `y`, `width`, "
        "`height` in points from the displayed page's bottom-left, as doc_stamp's). Metadata and earlier revisions are dropped. "
        "Returns the copy's `path` and the `count` of strikes."
    ),
    read_only=False,
)
OCR: Final = MCPTool(
    name="doc_ocr",
    title="Read a scan",
    description=(
        "The words of a scanned PDF or an image by `path` (`pages` from 0, all when empty; `dpi` a PDF page is drawn at, "
        "72-300, default 150), each with its box `[left, bottom, right, top]` in points on the displayed page, origin "
        "bottom-left — where doc_stamp places things —, and each page's `text`. An image is one page, a pixel a point."
    ),
)
SIGN: Final = MCPTool(
    name="doc_sign",
    title="Sign a PDF cryptographically",
    description=(
        "A PDF by `path` signed in PAdES with the key this server holds — who sealed it and that it was not changed "
        "since; a viewer validates it. Invisible; with `at` (as doc_stamp's) and one of `image`, `text` or `photo` its "
        "appearance is drawn there first (`lines` as doc_signature's). Returns the signed copy's `path`. Any later edit breaks it."
    ),
    read_only=False,
)


##### ROUTES #####
def routes(*tools: tuple[MCPTool, Callable[..., Any]]) -> tuple[HTTPRouteHandler, ...]:
    """The route of each tool over its handler."""
    return tuple(
        tool.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(handler)
        for tool, handler in tools
    )


ROUTES: tuple[HTTPRouteHandler, ...] = routes(
    (CONVERT, router.convert),
    (INSPECT, router.inspect),
    (MERGE, router.merge),
    (SPLIT, router.split),
    (FILL, router.fill),
    (RENDER, router.render),
    (STAMP, router.stamp),
    (SIGNATURE, router.signature),
    (COMPOSE, router.compose),
    (REDACT, router.redact),
)
### served only where the engine is on (OCR_ENABLED).
OCR_ROUTES: tuple[HTTPRouteHandler, ...] = routes((OCR, router.ocr))
### served only where a key is set (SIGN_P12).
SIGN_ROUTES: tuple[HTTPRouteHandler, ...] = routes((SIGN, router.sign))
