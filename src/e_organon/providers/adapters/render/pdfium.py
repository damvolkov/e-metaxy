"""providers/adapters/render/pdfium: PDF pages as PNG, and where a text sits on them, through pypdfium2 (PDFium, the engine
Chrome renders with).

PDFium is not thread-safe: every render takes the adapter's lock, off the loop in a worker thread."""

import io
import threading
from typing import ClassVar, Final, Self

import anyio
import pypdfium2 as pdfium

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload
from e_organon.ports.render import TextHit

### PDF user space is 72 points per inch.
POINTS: Final[float] = 72.0


##### ADAPTER #####
class PdfiumAdapter:
    """In-process rendering, one page at a time under one lock."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pdfium", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.SERIAL)

    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock = threading.Lock()

    ##### PRIVATE #####

    def _common_open(self, data: bytes) -> pdfium.PdfDocument:
        try:
            return pdfium.PdfDocument(data)
        except pdfium.PdfiumError as error:
            msg = f"not a readable PDF: {error}"
            raise ParseError(msg) from error

    def _count_read(self, data: bytes) -> int:
        with self._lock:
            return len(self._common_open(data))

    def _page_draw(self, data: bytes, index: int, dpi: int) -> bytes:
        with self._lock:
            document = self._common_open(data)
            match 0 <= index < len(document):
                case False:
                    msg = f"page {index} is outside 0-{len(document) - 1}"
                    raise ParseError(msg)
            image = document[index].render(scale=dpi / POINTS).to_pil()
            sink = io.BytesIO()
            image.save(sink, format="PNG", optimize=True)
            return sink.getvalue()

    @staticmethod
    def _find_page(page: pdfium.PdfPage, index: int, text: str) -> list[TextHit]:
        """Every match on the page, case ignored: the union of its characters' boxes."""
        textpage = page.get_textpage()
        matches = iter(textpage.search(text, match_case=False).get_next, None)
        boxes = [[textpage.get_charbox(i) for i in range(start, start + count)] for start, count in matches]
        return [
            TextHit(
                page=index,
                rect=(
                    min(b[0] for b in chars),
                    min(b[1] for b in chars),
                    max(b[2] for b in chars),
                    max(b[3] for b in chars),
                ),
            )
            for chars in boxes
            if chars
        ]

    def _find_scan(self, data: bytes, text: str) -> tuple[TextHit, ...]:
        with self._lock:
            document = self._common_open(data)
            return tuple(hit for index in range(len(document)) for hit in self._find_page(document[index], index, text))

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def count(self, data: bytes) -> int:
        return await anyio.to_thread.run_sync(self._count_read, data)

    async def page(self, data: bytes, index: int, dpi: int) -> bytes:
        return await anyio.to_thread.run_sync(self._page_draw, data, index, dpi)

    async def find(self, data: bytes, text: str) -> tuple[TextHit, ...]:
        return await anyio.to_thread.run_sync(self._find_scan, data, text)
