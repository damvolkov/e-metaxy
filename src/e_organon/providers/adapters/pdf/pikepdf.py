"""providers/adapters/pdf/pikepdf: the PDF's structure through pikepdf (qpdf, C++) — read, merge, split, fill.

Every call opens the bytes, edits in memory and saves to bytes, off the loop in a worker thread: qpdf holds the GIL
only at its edges. A field is set through qpdf's form layer (`Pdf.acroform`), which keeps a checkbox's value and its
widget's state together and draws the appearances, so a viewer shows the value without re-rendering. qpdf's own error
is the tree's `ParseError`."""

import io
from contextlib import ExitStack
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

import anyio
import pikepdf

from e_organon.infra.errors import ParseError
from e_organon.ports.pdf import PdfField, PdfInfo
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

KINDS: Final[Mapping[str, str]] = MappingProxyType({"/Tx": "text", "/Ch": "choice", "/Sig": "signature"})
### /Ff bits of a button field (PDF 32000-1, table 226): a radio group, a push button; neither is a checkbox.
RADIO: Final[int] = 1 << 15
PUSH: Final[int] = 1 << 16
CHECKED: Final[frozenset[str]] = frozenset({"1", "true", "on", "yes", "x"})


##### ADAPTER #####
class PikepdfAdapter:
    """In-process PDF editing; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pikepdf", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

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

    @classmethod
    def _info_read(cls, data: bytes) -> PdfInfo:
        with cls._common_open(data) as pdf:
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

    ##### PRIVATE — editing #####

    @staticmethod
    def _merge_join(parts: Sequence[bytes]) -> bytes:
        with ExitStack() as stack:
            merged = stack.enter_context(pikepdf.new())
            sources = [stack.enter_context(PikepdfAdapter._common_open(part)) for part in parts]
            ### add_pages_from carries the AcroForm with the pages (and renames colliding fields): extend() would drop it.
            _ = [merged.add_pages_from(source) for source in sources]
            return PikepdfAdapter._common_save(merged)

    @staticmethod
    def _split_cut(data: bytes, ranges: Sequence[tuple[int, int]]) -> tuple[bytes, ...]:
        with PikepdfAdapter._common_open(data) as pdf:
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

    @staticmethod
    def _fill_write(data: bytes, values: Mapping[str, str]) -> bytes:
        with PikepdfAdapter._common_open(data) as pdf:
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

    ##### PRIVATE — common #####

    @staticmethod
    def _common_open(data: bytes) -> pikepdf.Pdf:
        try:
            return pikepdf.open(io.BytesIO(data))
        except pikepdf.PdfError as error:
            msg = f"not a readable PDF: {error}"
            raise ParseError(msg) from error

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
