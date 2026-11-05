"""e_organon.services.doc.ocr: doc/ocr — the words of a scanned PDF or an image, each with its box, and the page's text.

A PDF page is drawn by the render port at `dpi` and read; an image is read as it is. Boxes leave in points on the page *as
displayed*, origin at its bottom-left, the terms `doc/stamp` places things in (an image is one page, a pixel a point), so
a word's box is where a stamp goes. The pixel budget (ORGANON_MAX_PIXELS) is checked before anything is decoded: from an
image's header, from a page's size in points and the resolution. Three steps: the file resolved, the budget measured, the
pages read."""

from functools import reduce
from typing import TYPE_CHECKING, Final

from e_organon.models.doc import OcrIn, OcrOut, OcrPageOut, OcrWordOut
from e_organon.models.error import ImageTooLargeError, PageNotFoundError
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.ports.ocr import OcrPort, OcrWord
    from e_organon.ports.pdf import PdfPort
    from e_organon.ports.render import RenderPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "measure", "read")
PDF: Final[bytes] = b"%PDF-"
### PDF user space is 72 points per inch.
POINTS: Final[float] = 72.0


##### TOOL #####
class OcrDocService(ToolFlow[OcrIn, OcrOut]):
    """doc/ocr: the pages of a scan read into words and text."""

    __slots__ = ("_files", "_max_pixels", "_ocr", "_pdf", "_render")

    def __init__(self, ocr: OcrPort, pdf: PdfPort, render: RenderPort, files: AllowedFiles, *, max_pixels: int) -> None:
        self._ocr, self._pdf, self._render = ocr, pdf, render
        self._files = files
        self._max_pixels = max_pixels

    ##### PRIVATE #####

    def _events_budget(self, width: float, height: float) -> None:
        match width * height <= self._max_pixels:
            case False:
                msg = f"{width:.0f}x{height:.0f} is {width * height:.0f} pixels; the limit is {self._max_pixels}"
                raise ImageTooLargeError(msg)

    @staticmethod
    def _events_fold(lines: list[list[OcrWordOut]], word: OcrWordOut) -> list[list[OcrWordOut]]:
        """The word on the last line when its centre sits within that line's last word's height, else on a new line."""
        last = lines[-1][-1] if lines else None
        centre = (word.box[1] + word.box[3]) / 2
        same = last is not None and last.box[1] <= centre <= last.box[3]
        return [*lines[:-1], [*lines[-1], word]] if same else [*lines, [word]]

    def _events_page(
        self, number: int, width: float, height: float, scale: float, words: tuple[OcrWord, ...]
    ) -> OcrPageOut:
        """The engine's words — pixels from the top-left — as points from the bottom-left, and the text they make."""
        placed = [
            OcrWordOut(
                text=each.text,
                box=(
                    each.box[0] * scale,
                    height - each.box[3] * scale,
                    each.box[2] * scale,
                    height - each.box[1] * scale,
                ),
            )
            for each in words
        ]
        lines = reduce(self._events_fold, placed, [])
        return OcrPageOut(
            page=number,
            width=width,
            height=height,
            text="\n".join(" ".join(w.text for w in line) for line in lines),
            words=placed,
        )

    async def _events_measure(self, raw: bytes, data: OcrIn) -> list[tuple[float, float]]:
        """Every page's displayed size — a PDF's in points, an image's in pixels —, the asked pages checked and budgeted."""
        match raw.startswith(PDF):
            case True:
                sizes = [geometry.size for geometry in await self._pdf.geometry(raw)]
                asked = data.pages or list(range(len(sizes)))
                gone = [index for index in asked if index >= len(sizes)]
                match gone:
                    case [first, *_]:
                        msg = f"page {first} is outside 0-{len(sizes) - 1}"
                        raise PageNotFoundError(msg)
                scale = data.dpi / POINTS
                _ = [self._events_budget(sizes[index][0] * scale, sizes[index][1] * scale) for index in asked]
                return sizes
            case _:
                size = await self._ocr.size(raw)
                self._events_budget(*size)
                return [size]

    async def _events_read(self, raw: bytes, data: OcrIn, sizes: list[tuple[float, float]]) -> OcrOut:
        match raw.startswith(PDF):
            case True:
                scale = data.dpi / POINTS
                return OcrOut(
                    pages=[
                        self._events_page(
                            index,
                            *sizes[index],
                            1 / scale,
                            await self._ocr.read(await self._render.page(raw, index, data.dpi), data.language),
                        )
                        for index in data.pages or range(len(sizes))
                    ]
                )
            case _:
                return OcrOut(pages=[self._events_page(0, *sizes[0], 1.0, await self._ocr.read(raw, data.language))])

    async def _events_run(self, data: OcrIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        _, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        sizes = await self._events_measure(raw, data)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        yield Done(result=await self._events_read(raw, data, sizes))
