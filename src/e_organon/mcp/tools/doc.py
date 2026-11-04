"""e_organon.mcp.tools.doc: the doc/ section as tools — the twin of `api/router/doc`, whose very handlers they are.

The MCP engine asks for JSON, so a tool always answers in batch: the result, or the `Failed` reason as its error."""

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

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    CONVERT.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(router.convert),
)
