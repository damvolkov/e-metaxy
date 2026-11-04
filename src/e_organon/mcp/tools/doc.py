"""e_organon.mcp.tools.doc: the doc/ section as tools — the twin of `api/router/doc`, whose very handlers they are.

The MCP engine asks for JSON, so a tool always answers in batch: the result, or the `Failed` reason as its error. Paths
are under the vault or the workspaces; a written file lands in the outbox, content-named, and is the next tool's input."""

from typing import Final

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

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    tool.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(handler)
    for tool, handler in (
        (CONVERT, router.convert),
        (INSPECT, router.inspect),
        (MERGE, router.merge),
        (SPLIT, router.split),
        (FILL, router.fill),
        (RENDER, router.render),
    )
)
