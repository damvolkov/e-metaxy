"""e_organon.mcp.refusals: a domain error as the tool's refusal — the API's own exceptions answer as they do, a tool adds none.

A refusal is the route's `detail`, which the MCP engine hands back as the tool's error text. The user records raise
Litestar's own `NotFoundException`; a domain error of a service becomes a row here, mapped to the status it earns."""

from typing import Final

import msgspec
from litestar.types import ExceptionHandlersMap

from e_organon.api.router.jobs import missing, refused
from e_organon.models.error import UnknownJobError, UnknownToolError

### every tool route's exception handlers, copied by each route (`MCPTool.route`): Litestar takes a mutable map.
REFUSALS: Final[ExceptionHandlersMap] = {
    UnknownJobError: missing,
    UnknownToolError: refused,
    msgspec.ValidationError: refused,
}
