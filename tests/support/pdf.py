"""tests/support/pdf: PDFs built in memory with pikepdf — blank pages, and a form whose fields cover every kind a PDF
names: a text field nested under a parent (`persona.nombre`), a checkbox drawn by a widget kid, a radio group, a push
button, a choice list and a signature field."""

import io
from typing import Any

import pikepdf
from pikepdf import Array, Dictionary, Name, String

A4: tuple[float, float] = (595, 842)
DA: str = "/Helv 10 Tf 0 g"


def _save(pdf: pikepdf.Pdf) -> bytes:
    sink = io.BytesIO()
    pdf.save(sink)
    return sink.getvalue()


def blank(pages: int) -> bytes:
    """A PDF of `pages` blank A4 pages."""
    with pikepdf.new() as pdf:
        _ = [pdf.add_blank_page(page_size=A4) for _ in range(pages)]
        return _save(pdf)


def form() -> bytes:
    """One page; the fields described above, their widgets on it."""
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=A4)

        def widget(rect: list[int], **extra: Any) -> Dictionary:
            return pdf.make_indirect(
                Dictionary(Type=Name.Annot, Subtype=Name.Widget, Rect=Array(rect), P=page.obj, F=4, **extra)
            )

        nombre = widget([100, 700, 300, 720], FT=Name.Tx, T=String("nombre"), DA=String(DA))
        persona = pdf.make_indirect(Dictionary(T=String("persona"), Kids=Array([nombre])))
        nombre.Parent = persona
        box = widget([100, 660, 115, 675], AS=Name.Off)
        acepta = pdf.make_indirect(Dictionary(FT=Name.Btn, T=String("acepta"), V=Name.Off, Kids=Array([box])))
        box.Parent = acepta
        box.AP = Dictionary(N=Dictionary(Yes=pdf.make_stream(b""), Off=pdf.make_stream(b"")))
        radio = widget([100, 620, 115, 635], FT=Name.Btn, T=String("sexo"), Ff=1 << 15)
        push = widget([100, 580, 160, 600], FT=Name.Btn, T=String("enviar"), Ff=1 << 16)
        choice = widget([100, 540, 300, 560], FT=Name.Ch, T=String("pais"), DA=String(DA))
        signature = widget([100, 480, 300, 520], FT=Name.Sig, T=String("firma"))
        page.obj.Annots = pdf.make_indirect(Array([nombre, box, radio, push, choice, signature]))
        pdf.Root.AcroForm = pdf.make_indirect(
            Dictionary(
                Fields=Array([persona, acepta, radio, push, choice, signature]),
                DA=String(DA),
                DR=Dictionary(
                    Font=Dictionary(Helv=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
                ),
            )
        )
        pdf.docinfo[Name.Title] = String("Solicitud")
        return _save(pdf)


def labelled(*, rotate: int = 0, crop: tuple[float, float, float, float] | None = None, second: bool = True) -> bytes:
    """One page with real text for a text search to find: `Firma:` at (100, 700) and, when `second`, `Firma: otra` at
    (100, 500) — user space, Helvetica 14 —, turned by `rotate` degrees and seen through the `crop` box if given."""
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=A4)
        page.obj.Resources = Dictionary(
            Font=Dictionary(F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
        )
        page.obj.Contents = pdf.make_stream(
            b"BT /F1 14 Tf 100 700 Td (Firma:) Tj ET"
            + (b" BT /F1 14 Tf 100 500 Td (Firma: otra) Tj ET" if second else b"")
        )
        page.obj.Rotate = rotate
        _ = crop and setattr(page.obj, "CropBox", Array(list(crop)))
        return _save(pdf)


def placements(data: bytes) -> list[tuple[float, ...]]:
    """The matrix `(w 0 0 h x y)` in force at every image drawn on the first page: the last `cm` before each `Do`."""
    found: list[tuple[float, ...]] = []
    last: tuple[float, ...] = ()
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for operands, operator in pikepdf.parse_content_stream(pdf.pages[0]):
            match str(operator):
                case "cm":
                    last = tuple(float(each) for each in operands)
                case "Do":
                    found.append(last)
    return found


def rotated(degrees: int) -> bytes:
    """One blank A4 page the viewer turns by `degrees`."""
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=A4)
        page.obj.Rotate = degrees
        return _save(pdf)
