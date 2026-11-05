"""ports/pdf: a PDF's structure — what it holds (pages, metadata, form fields) and the edits that keep it a PDF: merge,
split, fill, stamp (an image — a PNG, its transparency kept — or a text drawn on a page, opaque or not).

Coordinates are PDF points, origin at the page's bottom-left, as the file stores them (`info`) — or as the page is displayed
(`PageGeometry`, what `stamp` is given); pages count from 0."""

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


class PageGeometry(msgspec.Struct, frozen=True, kw_only=True):
    """How a page is seen: its visible box in user space — `left`, `bottom`, `right`, `top`, the crop box, else the media box —
    and `rotate` (0, 90, 180, 270: degrees clockwise the viewer turns it). A PDF's own rectangles (a field's, a text's) are in
    user space; a person places things on the page *as displayed*: origin at the visible page's bottom-left after the
    rotation. `shown` and `user` convert a point either way; `axes` are the user-space directions of the displayed x and y."""

    left: float
    bottom: float
    right: float
    top: float
    rotate: int = 0

    @property
    def size(self) -> tuple[float, float]:
        """The displayed page's width and height."""
        width, height = self.right - self.left, self.top - self.bottom
        return (height, width) if self.rotate in {90, 270} else (width, height)

    def shown(self, x: float, y: float) -> tuple[float, float]:
        """A user-space point as displayed."""
        rx, ry = x - self.left, y - self.bottom
        width, height = self.right - self.left, self.top - self.bottom
        match self.rotate:
            case 90:
                return ry, width - rx
            case 180:
                return width - rx, height - ry
            case 270:
                return height - ry, rx
            case _:
                return rx, ry

    def user(self, x: float, y: float) -> tuple[float, float]:
        """A displayed point in user space."""
        width, height = self.right - self.left, self.top - self.bottom
        match self.rotate:
            case 90:
                rx, ry = width - y, x
            case 180:
                rx, ry = width - x, height - y
            case 270:
                rx, ry = y, height - x
            case _:
                rx, ry = x, y
        return self.left + rx, self.bottom + ry

    @property
    def axes(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """User-space unit directions of the displayed x axis and y axis."""
        match self.rotate:
            case 90:
                return (0.0, 1.0), (-1.0, 0.0)
            case 180:
                return (-1.0, 0.0), (0.0, -1.0)
            case 270:
                return (0.0, -1.0), (1.0, 0.0)
            case _:
                return (1.0, 0.0), (0.0, 1.0)


class PdfBox(msgspec.Struct, frozen=True, kw_only=True):
    """Where a stamp goes on a page *as displayed* (`PageGeometry`): the bottom-left corner `x`, `y` and a `width`; the
    `height` when given, else the one that keeps the image's aspect ratio. An image given both is fitted inside, centred; a
    text is that high."""

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

    async def geometry(self, data: bytes) -> tuple[PageGeometry, ...]: ...

    async def stamp(
        self, data: bytes, page: int, box: PdfBox, *, image: bytes | None, text: str | None, opacity: float
    ) -> bytes: ...
