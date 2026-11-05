"""providers/adapters/pdf/pikepdf: the PDF's structure through pikepdf (qpdf, C++) — read, merge, split, fill, stamp.

Every call opens the bytes, edits in memory and saves to bytes, off the loop in a worker thread: qpdf holds the GIL
only at its edges. A field is set through qpdf's form layer (`Pdf.acroform`), which keeps a checkbox's value and its
widget's state together and draws the appearances, so a viewer shows the value without re-rendering. qpdf's own error
is the tree's `ParseError`.

A stamp is drawn after the page's own content, which is wrapped in a saved graphics state so nothing it left open bends
the stamp: an image is an image XObject (RGB, its alpha an `SMask`) painted through the matrix `(w 0 0 h x y)`; a text is
Helvetica in WinAnsi, black, its size the box's height (12 without), shrunk so about half an em a character fits the
width; an opacity below 1 is an `ExtGState`. The box is *as displayed*: the page's `/Rotate` and its crop box are applied
(`PageGeometry`), so the stamp stands upright on a rotated page and lands where a person's coordinates say on a cropped one."""

import io
import warnings
from contextlib import ExitStack
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

import anyio
import pikepdf
from PIL import Image, UnidentifiedImageError

from e_organon.infra.errors import ParseError
from e_organon.ports.pdf import PageGeometry, PdfBox, PdfField, PdfInfo
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

KINDS: Final[Mapping[str, str]] = MappingProxyType({"/Tx": "text", "/Ch": "choice", "/Sig": "signature"})
### /Ff bits of a button field (PDF 32000-1, table 226): a radio group, a push button; neither is a checkbox.
RADIO: Final[int] = 1 << 15
PUSH: Final[int] = 1 << 16
CHECKED: Final[frozenset[str]] = frozenset({"1", "true", "on", "yes", "x"})
### a stamped text: its size without a box height, an average glyph's width in ems, the baseline's rise above the box in ems.
DEFAULT_SIZE: Final[float] = 12.0
EM: Final[float] = 0.5
BASELINE: Final[float] = 0.25
### what a document may hold before any tool walks it: pages of a PDF (a page tree can name one page twenty thousand times in a
### few hundred kilobytes), pixels of a stamped image (decoding allocates in proportion). The root sets both from the settings.
PAGES: Final[int] = 5_000
PIXELS: Final[int] = 40_000_000


##### ADAPTER #####
class PikepdfAdapter:
    """In-process PDF editing; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pikepdf", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

    __slots__ = ("_max_pages", "_max_pixels")

    def __init__(self, *, max_pages: int = PAGES, max_pixels: int = PIXELS) -> None:
        self._max_pages, self._max_pixels = max_pages, max_pixels

    ##### PRIVATE — reading #####

    @staticmethod
    def _info_kind(node: Any) -> str:
        flags = int(node.get("/Ff", 0))
        match str(node.get("/FT", "")):
            case "/Btn":
                return "radio" if flags & RADIO else "button" if flags & PUSH else "checkbox"
            case kind:
                return KINDS.get(kind, "")

    @classmethod
    def _info_walk(cls, node: Any, prefix: str, kind: str, annots: Mapping[Any, int]) -> Iterator[PdfField]:
        """The terminal fields under `node`, named by their full dotted path; a kid without `/T` is a widget."""
        part = str(node.get("/T", ""))
        name = f"{prefix}.{part}" if prefix and part else part or prefix
        kind = cls._info_kind(node) or kind
        kids = [kid for kid in node.get("/Kids", ()) if "/T" in kid]
        yield from (
            (field for kid in kids for field in cls._info_walk(kid, name, kind, annots))
            if kids
            else (cls._info_leaf(node, name, kind, annots),)
        )

    @staticmethod
    def _info_leaf(node: Any, name: str, kind: str, annots: Mapping[Any, int]) -> PdfField:
        widget = node if "/Rect" in node else next(iter(node.get("/Kids", ())), node)
        rect = tuple(float(edge) for edge in widget.get("/Rect", (0, 0, 0, 0)))
        value = str(node.get("/V", "")).removeprefix("/")
        return PdfField(
            name=name,
            kind=kind,
            page=annots.get(widget.objgen, 0),
            rect=(rect[0], rect[1], rect[2], rect[3]),
            value=value,
        )

    def _info_read(self, data: bytes) -> PdfInfo:
        cls = type(self)
        with self._common_open(data) as pdf:
            annots = {
                annot.objgen: index for index, page in enumerate(pdf.pages) for annot in page.obj.get("/Annots", ())
            }
            roots = pdf.Root.get("/AcroForm", {}).get("/Fields", ())
            return PdfInfo(
                pages=tuple(
                    (float(page.mediabox[2] - page.mediabox[0]), float(page.mediabox[3] - page.mediabox[1]))
                    for page in pdf.pages
                ),
                metadata={str(key).removeprefix("/"): str(value) for key, value in pdf.docinfo.items()},
                fields=tuple(field for root in roots for field in cls._info_walk(root, "", "", annots)),
            )

    def _geometry_read(self, data: bytes) -> tuple[PageGeometry, ...]:
        with self._common_open(data) as pdf:
            return tuple(self._geometry_of(page) for page in pdf.pages)

    ##### PRIVATE — editing #####

    def _merge_join(self, parts: Sequence[bytes]) -> bytes:
        with ExitStack() as stack:
            merged = stack.enter_context(pikepdf.new())
            sources = [stack.enter_context(self._common_open(part)) for part in parts]
            ### the parts are each within the budget, the whole is not: a merge of many is as heavy as one that is many.
            _ = self._common_pages(sum(len(source.pages) for source in sources))
            ### add_pages_from carries the AcroForm with the pages (and renames colliding fields): extend() would drop it.
            _ = [merged.add_pages_from(source) for source in sources]
            return PikepdfAdapter._common_save(merged)

    def _split_cut(self, data: bytes, ranges: Sequence[tuple[int, int]]) -> tuple[bytes, ...]:
        with self._common_open(data) as pdf:
            return tuple(PikepdfAdapter._split_part(pdf, first, last) for first, last in ranges)

    @staticmethod
    def _split_part(pdf: pikepdf.Pdf, first: int, last: int) -> bytes:
        count = len(pdf.pages)
        match 0 <= first <= last < count:
            case False:
                msg = f"pages {first}-{last} are outside 0-{count - 1}"
                raise ParseError(msg)
        with pikepdf.new() as part:
            _ = part.add_pages_from(pdf, range(first, last + 1))
            return PikepdfAdapter._common_save(part)

    @staticmethod
    def _fill_state(form: Any, field: Any, value: str) -> Any:
        """A checkbox's value as the name of its widget's state: its own on-state when checked, `/Off` when not."""
        states = (
            str(state)
            for widget in form.get_annotations_for_field(field)
            for state in widget.obj.get("/AP", {}).get("/N", {}).keys()  # noqa: SIM118 — a pikepdf Dictionary
            if str(state) != "/Off"
        )
        return pikepdf.Name(next(states, "/Yes") if value.strip().lower() in CHECKED else "/Off")

    @staticmethod
    def _fill_set(form: Any, field: Any, value: str) -> None:
        field.set_value(PikepdfAdapter._fill_state(form, field, value) if field.is_checkbox else pikepdf.String(value))

    def _fill_write(self, data: bytes, values: Mapping[str, str]) -> bytes:
        with self._common_open(data) as pdf:
            form = pdf.acroform
            found = {name: form.get_fields_with_qualified_name(name) for name in values}
            unknown = sorted(name for name, fields in found.items() if not fields)
            match unknown:
                case [_, *_]:
                    names = sorted({field.fully_qualified_name for field in form.fields})
                    msg = f"no field named {', '.join(unknown)}; the form has {', '.join(names) or 'none'}"
                    raise ParseError(msg)
            _ = [
                PikepdfAdapter._fill_set(form, field, values[name])
                for name, fields in found.items()
                for field in fields
            ]
            form.generate_appearances_if_needed()
            return PikepdfAdapter._common_save(pdf)

    @staticmethod
    def _stamp_inherited(node: Any, key: str) -> Any:
        """A page attribute, from the page or the nearest page tree node above it that has it."""
        match node.get(key):
            case None:
                parent = node.get("/Parent")
                return None if parent is None else PikepdfAdapter._stamp_inherited(parent, key)
            case found:
                return found

    @staticmethod
    def _geometry_of(page: pikepdf.Page) -> PageGeometry:
        left, bottom, right, top = (float(edge) for edge in page.cropbox)
        turn = PikepdfAdapter._stamp_inherited(page.obj, "/Rotate")
        return PageGeometry(
            left=min(left, right),
            bottom=min(bottom, top),
            right=max(left, right),
            top=max(bottom, top),
            rotate=int(turn or 0) % 360,
        )

    @staticmethod
    def _stamp_fit(box: PdfBox, width: int, height: int) -> tuple[float, float, float, float]:
        """The image's rectangle `(x, y, w, h)`: the box's width at the image's aspect, or the image fitted inside the box."""
        match box.height:
            case None:
                return box.x, box.y, box.width, box.width * height / width
            case tall:
                scale = min(box.width / width, tall / height)
                drawn_w, drawn_h = width * scale, height * scale
                return box.x + (box.width - drawn_w) / 2, box.y + (tall - drawn_h) / 2, drawn_w, drawn_h

    def _stamp_image(self, pdf: pikepdf.Pdf, data: bytes) -> tuple[pikepdf.Object, int, int]:
        """The image XObject of a PNG (RGB, its alpha an SMask), and its pixel size; the pixels are counted from the header
        first and a picture over the budget is refused unread."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                opened = Image.open(io.BytesIO(data))
            match opened.width * opened.height <= self._max_pixels:
                case False:
                    msg = f"{opened.width}x{opened.height} is {opened.width * opened.height} pixels; the limit is {self._max_pixels}"
                    raise ParseError(msg)
            picture = opened.convert("RGBA")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error
        base = {"/Type": pikepdf.Name.XObject, "/Subtype": pikepdf.Name.Image, "/BitsPerComponent": 8}
        size = {"/Width": picture.width, "/Height": picture.height}
        mask = pdf.make_stream(picture.getchannel("A").tobytes())
        mask.update({**base, **size, "/ColorSpace": pikepdf.Name.DeviceGray})
        image = pdf.make_stream(picture.convert("RGB").tobytes())
        image.update({**base, **size, "/ColorSpace": pikepdf.Name.DeviceRGB, "/SMask": mask})
        return image, picture.width, picture.height

    @staticmethod
    def _stamp_matrix(geometry: PageGeometry, x: float, y: float, width: float, height: float) -> list[float]:
        """The matrix that draws a `width` x `height` unit-square thing upright with its bottom-left at the displayed point
        `x`, `y`: its axes are the page's displayed axes in user space, its origin that point in user space."""
        (ax, ay), (bx, by) = geometry.axes
        origin = geometry.user(x, y)
        return [width * ax, width * ay, height * bx, height * by, origin[0], origin[1]]

    @staticmethod
    def _stamp_text(page: pikepdf.Page, pdf: pikepdf.Pdf, geometry: PageGeometry, box: PdfBox, text: str) -> list[Any]:
        """The operators that write `text` in Helvetica inside the box."""
        font = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
                Encoding=pikepdf.Name.WinAnsiEncoding,
            )
        )
        name = page.add_resource(font, pikepdf.Name.Font, prefix="Org")
        size = min(box.height or DEFAULT_SIZE, box.width / (EM * max(len(text), 1)))
        shown = pikepdf.String(text.encode("cp1252", errors="replace"))
        return [
            ([], pikepdf.Operator("BT")),
            ([name, size], pikepdf.Operator("Tf")),
            ([0], pikepdf.Operator("g")),
            (PikepdfAdapter._stamp_matrix(geometry, box.x, box.y + BASELINE * size, 1, 1), pikepdf.Operator("Tm")),
            ([shown], pikepdf.Operator("Tj")),
            ([], pikepdf.Operator("ET")),
        ]

    def _stamp_draw(
        self, pdf: pikepdf.Pdf, index: int, box: PdfBox, *, image: bytes | None, text: str | None, opacity: float
    ) -> None:
        count = len(pdf.pages)
        match 0 <= index < count:
            case False:
                msg = f"page {index} is outside 0-{count - 1}"
                raise ParseError(msg)
        page = pdf.pages[index]
        geometry = PikepdfAdapter._geometry_of(page)
        drawn: list[Any] = []
        match (image, text):
            case (bytes() as picture, _):
                xobject, width, height = self._stamp_image(pdf, picture)
                x, y, w, h = PikepdfAdapter._stamp_fit(box, width, height)
                name = page.add_resource(xobject, pikepdf.Name.XObject, prefix="Org")
                drawn = [
                    (PikepdfAdapter._stamp_matrix(geometry, x, y, w, h), pikepdf.Operator("cm")),
                    ([name], pikepdf.Operator("Do")),
                ]
            case (_, str() as words):
                drawn = PikepdfAdapter._stamp_text(page, pdf, geometry, box, words)
        state = page.add_resource(
            pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, ca=opacity, CA=opacity),
            pikepdf.Name.ExtGState,
            prefix="Org",
        )
        gs = [([state], pikepdf.Operator("gs"))] if opacity < 1 else []
        wrap = [([], pikepdf.Operator("q")), *gs, *drawn, ([], pikepdf.Operator("Q"))]
        page.contents_add(pdf.make_stream(pikepdf.unparse_content_stream([([], pikepdf.Operator("q"))])), prepend=True)
        page.contents_add(pdf.make_stream(pikepdf.unparse_content_stream([([], pikepdf.Operator("Q")), *wrap])))

    def _stamp_write(
        self, data: bytes, index: int, box: PdfBox, *, image: bytes | None, text: str | None, opacity: float
    ) -> bytes:
        with self._common_open(data) as pdf:
            self._stamp_draw(pdf, index, box, image=image, text=text, opacity=opacity)
            return PikepdfAdapter._common_save(pdf)

    ##### PRIVATE — common #####

    def _common_pages(self, count: int) -> int:
        """`count` pages when within the budget, else a `ParseError`: a page tree is walked page by page by every tool."""
        match count <= self._max_pages:
            case False:
                msg = f"{count} pages; the limit is {self._max_pages}"
                raise ParseError(msg)
        return count

    def _common_open(self, data: bytes) -> pikepdf.Pdf:
        try:
            pdf = pikepdf.open(io.BytesIO(data))
        except pikepdf.PdfError as error:
            msg = f"not a readable PDF: {error}"
            raise ParseError(msg) from error
        try:
            _ = self._common_pages(len(pdf.pages))
        except ParseError:
            pdf.close()
            raise
        return pdf

    @staticmethod
    def _common_save(pdf: pikepdf.Pdf) -> bytes:
        sink = io.BytesIO()
        pdf.save(sink)
        return sink.getvalue()

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def info(self, data: bytes) -> PdfInfo:
        return await anyio.to_thread.run_sync(self._info_read, data)

    async def merge(self, parts: Sequence[bytes]) -> bytes:
        return await anyio.to_thread.run_sync(self._merge_join, parts)

    async def split(self, data: bytes, ranges: Sequence[tuple[int, int]]) -> tuple[bytes, ...]:
        return await anyio.to_thread.run_sync(self._split_cut, data, ranges)

    async def fill(self, data: bytes, values: Mapping[str, str]) -> bytes:
        return await anyio.to_thread.run_sync(self._fill_write, data, values)

    async def geometry(self, data: bytes) -> tuple[PageGeometry, ...]:
        return await anyio.to_thread.run_sync(self._geometry_read, data)

    async def stamp(
        self, data: bytes, page: int, box: PdfBox, *, image: bytes | None, text: str | None, opacity: float
    ) -> bytes:
        return await anyio.to_thread.run_sync(
            partial(self._stamp_write, data, page, box, image=image, text=text, opacity=opacity)
        )
