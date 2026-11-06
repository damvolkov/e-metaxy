"""ports/redact: text, images and metadata taken out of a PDF for good — what a black box drawn over them does not do.

A redaction is removal: after it the file no longer holds what was struck, whichever way it is read (a text extractor, the
content streams, the images, the metadata, an earlier revision of the file). A strike is a text — a literal, case ignored, or a
regular expression — or a box *as displayed* (`ports/pdf.PageGeometry`: origin at the visible page's bottom-left, in points)."""

from typing import TYPE_CHECKING, Annotated, Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider

if TYPE_CHECKING:
    from collections.abc import Sequence


##### VALUES #####
PAGE = Annotated[int, msgspec.Meta(ge=0)]
POINTS = Annotated[float, msgspec.Meta(gt=0)]


class RedactBox(msgspec.Struct, frozen=True, kw_only=True):
    """A box on `page` (from 0): its bottom-left corner `x`, `y` and its `width` and `height`, in points as displayed."""

    page: PAGE
    x: float
    y: float
    width: POINTS
    height: POINTS


class Redaction(msgspec.Struct, frozen=True, kw_only=True):
    """The redacted PDF and how many strikes it took: a text match is one each, a box is one each."""

    data: bytes
    count: int


##### PORT #####
@runtime_checkable
class RedactPort(Provider, Protocol):
    """`redact` the `terms` (literals, or regular expressions when `regex`) found on `pages` (from 0; every page when empty) and
    the `boxes`: the text and the images under them are removed, the metadata and the file's
    earlier revisions dropped, the same bytes for the same input. A PDF that cannot be read, or whose regex does not end in
    time, is a `ParseError`."""

    async def redact(
        self,
        data: bytes,
        *,
        terms: Sequence[str],
        regex: bool,
        boxes: Sequence[RedactBox],
        pages: Sequence[int],
    ) -> Redaction: ...
