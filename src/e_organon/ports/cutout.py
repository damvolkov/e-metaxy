"""ports/cutout: ink on a photographed sheet, lifted off it — what a signature, a stamp or a drawing needs to be placed on
another page."""

from typing import Protocol, runtime_checkable

from e_organon.ports.provider import Provider


##### PORT #####
@runtime_checkable
class CutoutPort(Provider, Protocol):
    """`size` is an image's width and height read from its header, nothing decoded; `cut` the PNG (RGBA) of the ink in a
    photo — opaque where it is, soft at its edges, clear elsewhere —, in the ink's own colour or black, cropped to the ink
    with a margin when `crop`. A photo that is no image, or a sheet with no ink, is a `ParseError`."""

    async def size(self, data: bytes) -> tuple[int, int]: ...

    async def cut(self, data: bytes, *, color: bool, crop: bool) -> bytes: ...
