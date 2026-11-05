"""tests/support/catalog: the shape of the catalog fixtures — a query asked of a service, read as the names it answers; the
tool list measured in bytes and tokens, and grown with tools of the same shapes."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from e_organon.infra.mcp.models import MCPEntry
    from e_organon.services.organon.find import FindOrganonService

type AtRest = Callable[[Sequence[MCPEntry]], tuple[int, int]]
type Grown = Callable[[Sequence[MCPEntry], int], list[MCPEntry]]


class Ranked(Protocol):
    async def __call__(self, service: FindOrganonService, query: str, section: str = "") -> list[str]: ...
