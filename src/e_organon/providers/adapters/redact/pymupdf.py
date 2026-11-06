"""providers/adapters/redact/pymupdf: text, images and metadata removed from a PDF for good, with PyMuPDF (MuPDF, C).

A strike is a rectangle, and `apply_redactions` is what makes it real: the glyphs under it are cut out of the content stream, the
pixels under it blanked in the image (an image wholly under it is dropped), not a black box drawn over them. A text is found
the way a person reads the page: the chars of the page in order, a newline between lines, matched by one regular expression
(a literal is escaped, case ignored, and any run of blanks in it matches any run of white space — a name wrapped over two
lines is found), and each match is struck line by line from the boxes of its chars. The metadata, the XMP and the thumbnails (a
thumbnail is the page as it was) are scrubbed, and the file is rewritten whole with unused objects collected, so an earlier
revision kept by an incremental update is gone. A caller's regex is code that can run forever: `regex` (C) stops it at the
deadline. A box is *as displayed* — origin at the visible page's bottom-left, rotation and crop box applied — and turned here
into MuPDF's page space. AGPL-3.0: PyMuPDF is used in-process, as a library."""

import hashlib
import time
from functools import partial, reduce
from itertools import chain, groupby
from operator import or_
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

import anyio
import pymupdf
import regex

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload
from e_organon.ports.redact import Redaction

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from e_organon.ports.redact import RedactBox

### the chars of a page as they are, ligatures broken into letters and nothing clipped to the page: a term hides in both.
FLAGS: Final[int] = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_LIGATURES & ~pymupdf.TEXT_MEDIABOX_CLIP
### a char of the page's text: the char, its box (None for the newline between lines) and its line.
### MuPDF's PDF_REDACT_IMAGE_PIXELS: the pixels under a strike blanked, the rest of the image kept (an image wholly under it goes).
PIXELS: Final[int] = 2
type Cell = tuple[str, pymupdf.Rect | None, int]


##### ADAPTER #####
class PymupdfAdapter:
    """In-process redaction; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pymupdf", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

    __slots__ = ("_max_pages", "_timeout")

    def __init__(self, *, timeout: float, max_pages: int) -> None:
        self._timeout, self._max_pages = timeout, max_pages

    ##### PRIVATE — redact #####

    def _redact_open(self, data: bytes) -> pymupdf.Document:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as error:
            msg = f"not a readable PDF: {error}"
            raise ParseError(msg) from error
        match (doc.is_pdf, bool(doc.needs_pass), doc.page_count <= self._max_pages):
            case (True, False, True):
                return doc
            case (False, _, _):
                msg = "not a readable PDF"
            case (_, True, _):
                msg = "the PDF is encrypted"
            case _:
                msg = f"{doc.page_count} pages; the limit is {self._max_pages}"
        doc.close()
        raise ParseError(msg)

    @staticmethod
    def _redact_pattern(terms: Sequence[str], *, literal: bool) -> list[Any]:
        try:
            return [
                regex.compile(
                    r"\s+".join(map(regex.escape, term.split())) if literal else term,
                    regex.IGNORECASE if literal else 0,
                )
                for term in terms
            ]
        except regex.error as error:
            msg = f"not a valid regular expression: {error}"
            raise ParseError(msg) from error

    @staticmethod
    def _redact_cells(page: pymupdf.Page) -> list[Cell]:
        lines = (line for block in page.get_text("rawdict", flags=FLAGS)["blocks"] for line in block.get("lines", ()))
        return list(
            chain.from_iterable(
                [(char["c"], pymupdf.Rect(char["bbox"]), n) for span in line["spans"] for char in span["chars"]]
                + [("\n", None, n)]
                for n, line in enumerate(lines)
            )
        )

    @staticmethod
    def _redact_lines(cells: Sequence[Cell]) -> Iterator[pymupdf.Rect]:
        """The rectangle of a match on each of its lines."""
        boxes = [(line, box) for _, box, line in cells if box is not None]
        return (reduce(or_, (box for _, box in group)) for _, group in groupby(boxes, key=lambda each: each[0]))

    def _redact_find(self, page: pymupdf.Page, patterns: Sequence[Any], deadline: float) -> list[list[pymupdf.Rect]]:
        """The rectangles of each match of any pattern on the page, a list a match."""
        cells = self._redact_cells(page)
        text = "".join(char for char, _, _ in cells)
        try:
            return [
                rects
                for pattern in patterns
                for found in pattern.finditer(text, timeout=max(deadline - time.monotonic(), 1e-3))
                if (rects := list(self._redact_lines(cells[found.start() : found.end()])))
            ]
        except TimeoutError as error:
            msg = f"a regular expression took longer than {self._timeout:g} s on a page and was stopped"
            raise ParseError(msg) from error

    @staticmethod
    def _redact_box(page: pymupdf.Page, box: RedactBox) -> pymupdf.Rect:
        """A box as displayed (bottom-left origin) in the page space MuPDF keeps its rectangles in (top-left, unturned)."""
        top = page.rect.height - box.y - box.height
        return (pymupdf.Rect(box.x, top, box.x + box.width, top + box.height) * page.derotation_matrix).normalize()

    def _redact_page(self, doc: pymupdf.Document, index: int) -> pymupdf.Page:
        match 0 <= index < doc.page_count:
            case True:
                return doc[index]
            case False:
                msg = f"the PDF has no page {index}"
                raise ParseError(msg)

    def _redact_strike(self, page: pymupdf.Page, rects: Sequence[pymupdf.Rect]) -> None:
        _ = [page.add_redact_annot(rect) for rect in rects]
        _ = rects and page.apply_redactions(images=PIXELS)

    def _redact_work(
        self, data: bytes, terms: Sequence[str], *, regexes: bool, boxes: Sequence[RedactBox], pages: Sequence[int]
    ) -> Redaction:
        deadline = time.monotonic() + self._timeout
        patterns = self._redact_pattern(terms, literal=not regexes)
        with self._redact_open(data) as doc:
            scope = pages or range(doc.page_count)
            found = (
                {index: self._redact_find(self._redact_page(doc, index), patterns, deadline) for index in scope}
                if patterns
                else {}
            )
            drawn = {each.page: [self._redact_box(self._redact_page(doc, each.page), each)] for each in boxes}
            _ = [
                self._redact_strike(
                    doc[index],
                    [rect for match in found.get(index, ()) for rect in match] + drawn.get(index, []),
                )
                for index in sorted(found.keys() | drawn.keys())
            ]
            doc.scrub(
                metadata=True,
                xml_metadata=True,
                thumbnails=True,
                attached_files=False,
                clean_pages=False,
                embedded_files=False,
                hidden_text=False,
                javascript=False,
                redactions=True,
                remove_links=False,
                reset_fields=False,
                reset_responses=False,
            )
            ### MuPDF mints a fresh trailer ID at every save: the input and the order give it, so the same input is the same bytes.
            ident = hashlib.sha256(repr((data, terms, regexes, boxes, pages)).encode()).hexdigest()[:32]
            doc.xref_set_key(-1, "ID", f"[<{ident}><{ident}>]")
            return Redaction(
                data=doc.tobytes(garbage=4, deflate=True, clean=True, no_new_id=True),
                count=sum(len(each) for each in found.values()) + len(boxes),
            )

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def redact(
        self,
        data: bytes,
        *,
        terms: Sequence[str],
        regex: bool,
        boxes: Sequence[RedactBox],
        pages: Sequence[int],
    ) -> Redaction:
        return await anyio.to_thread.run_sync(
            partial(self._redact_work, data, terms, regexes=regex, boxes=boxes, pages=pages)
        )
