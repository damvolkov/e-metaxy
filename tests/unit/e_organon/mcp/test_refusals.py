"""tests/unit/e_organon/mcp/refusals: the table of domain errors a tool refuses with — a row per error a service adds, and
copied by every tool route so no route mutates the shared one."""

import msgspec

from e_organon.api.router.jobs import missing, refused
from e_organon.mcp.refusals import REFUSALS
from e_organon.mcp.registry import ROUTES
from e_organon.models.error import UnknownJobError, UnknownToolError


async def test_refusals_hold_a_row_per_error_a_service_adds() -> None:
    assert dict(REFUSALS) == {
        UnknownJobError: missing,
        UnknownToolError: refused,
        msgspec.ValidationError: refused,
    }


async def test_refusals_are_copied_by_each_tool_route() -> None:
    assert all(route.exception_handlers is not REFUSALS for route in ROUTES)
