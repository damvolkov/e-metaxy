"""tests/support/redact: PDFs with something to take out, and the three ways a leak is looked for — built and read with none of the
code under test (pikepdf writes them; pdfium, pikepdf's content streams and MuPDF read them back).

`secret` is a two-page PDF: page 0 says `Cliente: ALFA-123 pagado` and `Otro: BRAVO-456` and draws a red 8 x 8 image in the box
`(100, 400, 200, 500)`, page 1 says `ALFA-123 en la pagina dos`; the title and the XMP both name `ALFA-123`."""

import io
from typing import TYPE_CHECKING, cast

import pikepdf
import pymupdf
import pypdfium2 as pdfium
from pikepdf import Array, Dictionary, Name, String

from support.shot import reddish, shot

if TYPE_CHECKING:
    from pathlib import Path

A4: tuple[float, float] = (595, 842)
TERM = "ALFA-123"
IMAGE_BOX: tuple[float, float, float, float] = (100, 400, 200, 500)


def _text(x: float, y: float, text: str) -> bytes:
    return f"BT /F1 14 Tf {x} {y} Td ({text}) Tj ET\n".encode()


def secret(*, rotate: int = 0, crop: tuple[float, float, float, float] | None = None) -> bytes:
    """The PDF described above, its first page turned by `rotate` and seen through `crop`."""
    with pikepdf.new() as pdf:
        font = Dictionary(F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
        red = pdf.make_stream(
            bytes([255, 0, 0] * 64),
            Type=Name.XObject,
            Subtype=Name.Image,
            Width=8,
            Height=8,
            ColorSpace=Name.DeviceRGB,
            BitsPerComponent=8,
        )
        first, second = pdf.add_blank_page(page_size=A4), pdf.add_blank_page(page_size=A4)
        first.obj.Resources = Dictionary(Font=font, XObject=Dictionary(Im0=red))
        first.obj.Contents = pdf.make_stream(
            _text(100, 700, f"Cliente: {TERM} pagado")
            + _text(100, 650, "Otro: BRAVO-456")
            + b"q 100 0 0 100 100 400 cm /Im0 Do Q\n"
        )
        second.obj.Resources = Dictionary(Font=font)
        second.obj.Contents = pdf.make_stream(_text(100, 700, f"{TERM} en la pagina dos"))
        first.obj.Rotate = rotate
        _ = crop and setattr(first.obj, "CropBox", Array(list(crop)))
        pdf.docinfo[Name.Title] = String(f"Informe {TERM}")
        with pdf.open_metadata() as meta:
            meta["dc:title"] = f"Informe {TERM}"
        sink = io.BytesIO()
        pdf.save(sink, deterministic_id=True)
        return sink.getvalue()


def aaaa() -> bytes:
    """One page that says `aaaa…` forty times over: what `(a|aa)+c` backtracks on for ever."""
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=A4)
        page.obj.Resources = Dictionary(
            Font=Dictionary(F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
        )
        page.obj.Contents = pdf.make_stream(_text(50, 700, "a" * 40))
        sink = io.BytesIO()
        pdf.save(sink, deterministic_id=True)
        return sink.getvalue()


def with_history(data: bytes, folder: Path) -> bytes:
    """`data` with an incremental update on top that retitles it: the first revision, `ALFA-123` in it, is still in the file."""
    path = folder / "history.pdf"
    path.write_bytes(data)
    with pymupdf.open(path) as doc:
        doc.set_metadata({"title": "limpio"})
        doc.saveIncr()
    return path.read_bytes()


def pdfium_text(data: bytes) -> str:
    """Every page's text as pdfium reads it."""
    return "\f".join(page.get_textpage().get_text_range() for page in pdfium.PdfDocument(data))


def mupdf_text(data: bytes) -> str:
    """Every page's text as MuPDF reads it."""
    with pymupdf.open(stream=data) as doc:
        return "\f".join(page.get_text() for page in doc)


def stream_text(data: bytes) -> str:
    """The strings the content streams of every page show, read operator by operator, and what a form XObject adds."""
    with pikepdf.open(io.BytesIO(data)) as pdf:
        return "\f".join(
            str(each)
            for page in pdf.pages
            for operands, operator in pikepdf.parse_content_stream(page)
            if str(operator) in {"Tj", "TJ", "'", '"'}
            for each in operands
        )


def red_left(data: bytes) -> bool:
    """Whether red shows in the first page's image box (user space, upright page) or any image object still holds red pixels."""
    page = shot(data)
    left, bottom, right, top = IMAGE_BOX
    shown = reddish(page[int(A4[1] - top) : int(A4[1] - bottom), int(left) : int(right)]).any()
    with pikepdf.open(io.BytesIO(data)) as pdf:
        raw = any(
            b"\xff\x00\x00" * 8 in pikepdf.PdfImage(cast("pikepdf.Stream", image)).as_pil_image().tobytes()
            for page in pdf.pages
            for image in page.Resources.get("/XObject", {}).values()
            if image.get("/Subtype") == "/Image"
        )
    return bool(shown or raw)
