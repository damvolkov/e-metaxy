"""ports/pdf: a PDF's structure — what it holds (pages, metadata, form fields) and the edits that keep it a PDF: merge,
split, fill, stamp (an image — a PNG, its transparency kept — or a text drawn on a page, opaque or not).

Coordinates are PDF points, origin at the page's bottom-left, as the file stores them; pages count from 0."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


##### VALUES #####
class PdfField(msgspec.Struct, frozen=True, kw_only=True):
    """One form field: its full name, kind (`text`, `checkbox`, `choice`, `radio`, `button`, `signature`), the page
    and rectangle of its first widget, and its current value."""

    name: str
    kind: str
    page: int
    rect: tuple[float, float, float, float]
    value: str = ""


class PdfBox(msgspec.Struct, frozen=True, kw_only=True):
    """Where a stamp goes on a page: the bottom-left corner `x`, `y` and a `width`; the `height` when given, else the one
    that keeps the image's aspect ratio. An image given both is fitted inside, centred; a text is that high."""

    x: float
    y: float
    width: float
    height: float | None = None


class PdfInfo(msgspec.Struct, frozen=True, kw_only=True):
    """A PDF at a glance: each page's size in points, its metadata, its form fields."""

    pages: tuple[tuple[float, float], ...]
    metadata: dict[str, str]
    fields: tuple[PdfField, ...]


##### PORT #####
@runtime_checkable
class PdfPort(Provider, Protocol):
    """Read and edit a PDF's structure; every edit answers the new document's bytes."""

    async def info(self, data: bytes) -> PdfInfo: ...

    async def merge(self, parts: Sequence[bytes]) -> bytes: ...

    async def split(self, data: bytes, ranges: Sequence[tuple[int, int]]) -> tuple[bytes, ...]: ...

    async def fill(self, data: bytes, values: Mapping[str, str]) -> bytes: ...

    async def stamp(
        self, data: bytes, page: int, box: PdfBox, *, image: bytes | None, text: str | None, opacity: float
    ) -> bytes: ...
