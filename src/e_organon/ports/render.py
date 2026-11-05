"""ports/render: a document page as an image — what an eye (a person, a thumbnail, a vision step) sees."""

from typing import Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider


##### VALUES #####
class TextHit(msgspec.Struct, frozen=True, kw_only=True):
    """Where a text was found: its page (from 0) and its box `(left, bottom, right, top)` in PDF points, origin at the
    page's bottom-left."""

    page: int
    rect: tuple[float, float, float, float]


##### PORT #####
@runtime_checkable
class RenderPort(Provider, Protocol):
    """Pages to PNG: `count` how many there are, `page` one of them at `dpi`; `find` where a text is on them, every match
    in page order, case ignored."""

    async def count(self, data: bytes) -> int: ...

    async def page(self, data: bytes, index: int, dpi: int) -> bytes: ...

    async def find(self, data: bytes, text: str) -> tuple[TextHit, ...]: ...
