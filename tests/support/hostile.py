"""tests/support/hostile: the hostile corpus's generator — `python -m support.hostile` rewrites `tests/resources/hostile/`.

Each file is small and nasty in one way, built without any of the code under test: an image whose header claims billions of
pixels (PNG and JPEG) and one that claims a hundred million, a PNG whose IDAT checksum is wrong, a PDF that runs JavaScript, opens a launch action and a URI
when opened, a PDF whose page tree names one page twenty thousand times, one cut in half, one that is only a header and
noise, an empty file of each kind, and a symlink out of the roots."""

import io
import struct
import zlib
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, String

HERE = Path(__file__).resolve().parents[1] / "resources" / "hostile"
PAGES = 20_000


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def _png(width: int, height: int, idat: bytes, *, crc_ok: bool = True) -> bytes:
    header = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    data = _chunk(b"IDAT", idat)
    return header + (data if crc_ok else data[:-4] + b"\0\0\0\0") + _chunk(b"IEND", b"")


def pixel_bomb_png() -> bytes:
    """65535 x 65535 grey, 4.3 gigapixels, in a few dozen bytes: the data is one row's worth."""
    return _png(65535, 65535, zlib.compress(b"\0" * 65536))


def big_header_png() -> bytes:
    """10000 x 10000 grey, 100 megapixels: under Pillow's own bomb limit (179 MP), over the service's budget (40 MP)."""
    return _png(10000, 10000, zlib.compress(b"\0" * 10001))


def pixel_bomb_jpg() -> bytes:
    """A JPEG whose start-of-frame says 65535 x 65535 and whose scan is empty."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 65535, 65535, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\xff\xd9"


def bad_crc_png() -> bytes:
    """A real 40 x 20 PNG with its IDAT checksum zeroed."""
    rows = b"".join(b"\0" + bytes(range(40)) for _ in range(20))
    return _png(40, 20, zlib.compress(rows), crc_ok=False)


def _save(pdf: pikepdf.Pdf) -> bytes:
    sink = io.BytesIO()
    pdf.save(sink)
    return sink.getvalue()


def javascript_pdf() -> bytes:
    """One page, and everything a PDF can run on its own: an OpenAction of JavaScript, a document-level script, a launch and a
    URI action on the page's open."""
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(595, 842))
        script = Dictionary(S=Name.JavaScript, JS=String("app.alert('hostile'); this.exportDataObject({cName:'x'});"))
        pdf.Root.OpenAction = pdf.make_indirect(script)
        pdf.Root.Names = Dictionary(JavaScript=Dictionary(Names=Array([String("boot"), pdf.make_indirect(script)])))
        page.obj.AA = Dictionary(
            O=Dictionary(S=Name.Launch, F=String("calc.exe")),
            C=Dictionary(S=Name.URI, URI=String("http://127.0.0.1:1/x")),
        )
        return _save(pdf)


def many_pages_pdf() -> bytes:
    """A page tree of `PAGES` kids that are all the same one page: small on disk, enormous to a tool that walks it."""
    with pikepdf.new() as pdf:
        pdf.add_blank_page(page_size=(595, 842))
        page = pdf.pages[0].obj
        pdf.Root.Pages.Kids = Array([page] * PAGES)
        pdf.Root.Pages.Count = PAGES
        return _save(pdf)


def truncated_pdf() -> bytes:
    """A PDF of three pages cut in half: no trailer, no cross-reference table."""
    with pikepdf.new() as pdf:
        _ = [pdf.add_blank_page(page_size=(595, 842)) for _ in range(3)]
        whole = _save(pdf)
    return whole[: len(whole) // 2]


def garbage_pdf() -> bytes:
    """The header of a PDF and then noise."""
    return b"%PDF-1.7\n" + bytes((i * 131 + 7) % 256 for i in range(2048))


FILES = {
    "pixel-bomb.png": pixel_bomb_png,
    "pixel-bomb.jpg": pixel_bomb_jpg,
    "big-header.png": big_header_png,
    "bad-crc.png": bad_crc_png,
    "javascript.pdf": javascript_pdf,
    "many-pages.pdf": many_pages_pdf,
    "truncated.pdf": truncated_pdf,
    "garbage.pdf": garbage_pdf,
    "empty.pdf": lambda: b"",
    "empty.png": lambda: b"",
    "not-an-image.png": lambda: b"this is text, not a picture\n",
}


def build(target: Path = HERE) -> None:
    """Write every file. The symlink `escape` is never committed — an absolute link breaks the sdist — the fixture makes it."""
    target.mkdir(parents=True, exist_ok=True)
    _ = [(target / name).write_bytes(make()) for name, make in FILES.items()]


if __name__ == "__main__":
    build()
