"""ports/render: a document page as an image — what an eye (a person, a thumbnail, a vision step) sees."""

from typing import Protocol, runtime_checkable

from e_organon.ports.provider import Provider


##### PORT #####
@runtime_checkable
class RenderPort(Provider, Protocol):
    """Pages to PNG: `count` how many there are, `page` one of them at `dpi`."""

    async def count(self, data: bytes) -> int: ...

    async def page(self, data: bytes, index: int, dpi: int) -> bytes: ...
