"""ports/ocr: the words on an image, each with its box — what a scan says and where."""

from typing import Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider


##### VALUES #####
class OcrWord(msgspec.Struct, frozen=True, kw_only=True):
    """A word and its box `(left, top, right, bottom)` in the image's pixels, origin at its top-left."""

    text: str
    box: tuple[float, float, float, float]


##### PORT #####
@runtime_checkable
class OcrPort(Provider, Protocol):
    """`size` is an image's width and height read from its header, nothing decoded; `read` its words in reading order. The
    `language` is a hint (`spa`, `eng`…) an engine may ignore. An image that is no image is a `ParseError`; one with no
    text has no words."""

    async def size(self, data: bytes) -> tuple[int, int]: ...

    async def read(self, data: bytes, language: str) -> tuple[OcrWord, ...]: ...
