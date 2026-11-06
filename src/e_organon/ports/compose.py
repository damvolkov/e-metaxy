"""ports/compose: a PDF made from a template and data — what an invoice, a letter or a report is, written once and filled."""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from e_organon.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


##### PORT #####
@runtime_checkable
class ComposePort(Provider, Protocol):
    """`compose` the template's `source` over `data` (JSON-shaped) into a PDF/A, the same bytes for the same input. The
    template may read files under `root` and nowhere else. A template that does not compile is a `ParseError` saying where."""

    async def compose(self, source: bytes, data: Mapping[str, Any], root: Path) -> bytes: ...
