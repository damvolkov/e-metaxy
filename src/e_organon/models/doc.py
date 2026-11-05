"""e_organon.models.doc: what the doc/ tools take and give — files by path, never bytes in the arguments.

Every path is under ORGANON_ROOTS; every file a tool writes lands in ORGANON_OUTBOX (inside a root), named by its
content, so one tool's output is the next one's input."""

from typing import Annotated, Any

import msgspec

from e_organon.ports.pdf import PdfField

PAGE = Annotated[int, msgspec.Meta(ge=0)]
DPI = Annotated[int, msgspec.Meta(ge=36, le=600)]


##### SHARED #####
class FileOut(msgspec.Struct, frozen=True, kw_only=True):
    """A file a tool wrote: where it is and how big."""

    path: str
    size: int


class FilesOut(msgspec.Struct, frozen=True, kw_only=True):
    """The files a tool wrote, in order."""

    files: list[FileOut]


##### CONVERT #####
class ConvertIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the document (`~` expands)."""

    path: str


class ConvertOut(msgspec.Struct, frozen=True, kw_only=True):
    """The document as Markdown: tables as tables, scans read, in page order."""

    name: str
    markdown: str


##### INSPECT #####
class InspectIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF."""

    path: str


class InspectOut(msgspec.Struct, frozen=True, kw_only=True):
    """A PDF at a glance: each page's size in points (bottom-left origin), its metadata, its form fields — each with
    its full name, kind, page, rectangle and value: what a `doc/fill` names."""

    name: str
    pages: list[tuple[float, float]]
    metadata: dict[str, str]
    fields: list[PdfField]


##### MERGE #####
class MergeIn(msgspec.Struct, frozen=True, kw_only=True):
    """`paths`: two or more PDFs, joined in this order; `name`: the output's stem."""

    paths: Annotated[list[str], msgspec.Meta(min_length=2)]
    name: str = "merged"


##### SPLIT #####
class SplitIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF; `ranges`: `[first, last]` page pairs, from 0, both included — one output each."""

    path: str
    ranges: Annotated[list[tuple[PAGE, PAGE]], msgspec.Meta(min_length=1)]


##### FILL #####
class FillIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF form; `values`: field full name → value (a checkbox takes `true`/`false`); see `doc/inspect`."""

    path: str
    values: Annotated[dict[str, str], msgspec.Meta(min_length=1)]


##### RENDER #####
class RenderIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF; `pages`: which, from 0 (all when empty); `dpi`: resolution, 36-600."""

    path: str
    pages: list[PAGE] = msgspec.field(default_factory=list)
    dpi: DPI = 110


##### STAMP #####
POINTS = Annotated[float, msgspec.Meta(gt=0)]
OPACITY = Annotated[float, msgspec.Meta(ge=0, le=1)]


class AtField(msgspec.Struct, frozen=True, kw_only=True, tag="field"):
    """An AcroForm field by its full name (`doc/inspect` lists them): its widget's page and rectangle."""

    field: str


class AtAnchor(msgspec.Struct, frozen=True, kw_only=True, tag="anchor"):
    """A text found on the pages, case ignored, the `occurrence`-th in page order: the stamp starts at its bottom-left
    corner plus `offset` (points, y up), fitted in the text's box or `width` wide."""

    anchor: str
    occurrence: Annotated[int, msgspec.Meta(ge=1)] = 1
    offset: tuple[float, float] = (0.0, 0.0)
    width: POINTS | None = None


class AtBox(msgspec.Struct, frozen=True, kw_only=True, tag="box"):
    """A box in PDF points from the bottom-left of `page` (from 0); no `height`, the image's aspect gives it."""

    page: PAGE
    x: float
    y: float
    width: POINTS
    height: POINTS | None = None


At = AtField | AtAnchor | AtBox


class StampIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF. `image` (a PNG path) or `text` (Helvetica), one of the two. `at`: where, tagged by `type`.
    `opacity`: 0-1."""

    path: str
    at: At
    image: str | None = None
    text: str | None = None
    opacity: OPACITY = 1.0

    def __post_init__(self) -> None:
        match (self.image is None, self.text is None):
            case (True, True) | (False, False):
                msg = "give an image or a text to stamp, one of the two"
                raise ValueError(msg)


##### SIGNATURE #####
class SignatureIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF to sign. `photo`: the signature on paper. `at`: where, as `doc/stamp`'s. `color`: the ink's own
    colour (off, black). `lines`: printed lines are not ink (off, a straight underline of the signature is kept)."""

    path: str
    photo: str
    at: At
    color: bool = True
    lines: bool = True


##### OCR #####
class OcrIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: a scanned PDF or an image. `pages`: which pages of a PDF, from 0 (all when empty). `language`: a hint for
    the engine, which today reads every Latin script alike. `dpi`: the resolution a PDF page is drawn at before it is read."""

    path: str
    pages: list[PAGE] = msgspec.field(default_factory=list)
    language: str = ""
    dpi: Annotated[int, msgspec.Meta(ge=72, le=300)] = 150


class OcrWordOut(msgspec.Struct, frozen=True, kw_only=True):
    """A word and its box `(left, bottom, right, top)` in points on the displayed page, origin at its bottom-left."""

    text: str
    box: tuple[float, float, float, float]


class OcrPageOut(msgspec.Struct, frozen=True, kw_only=True):
    """A page read: its number (from 0), its displayed size in points, its text — lines apart — and its words."""

    page: int
    width: float
    height: float
    text: str
    words: list[OcrWordOut]


class OcrOut(msgspec.Struct, frozen=True, kw_only=True):
    """The pages read, in order. An image is one page, one pixel a point."""

    pages: list[OcrPageOut]


##### SIGN #####
class SignIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the PDF to sign. Invisible by default; give `at` (as `doc/stamp`'s) and one of `image` (a PNG path), `text`
    or `photo` (a signature on paper, cut out as `doc/signature` does, `lines` as there) and its appearance is drawn there first."""

    path: str
    at: At | None = None
    image: str | None = None
    text: str | None = None
    photo: str | None = None
    lines: bool = True

    def __post_init__(self) -> None:
        match (self.at is None, sum(each is not None for each in (self.image, self.text, self.photo))):
            case (True, 0) | (False, 1):
                pass
            case _:
                msg = "give `at` with exactly one of image, text or photo for a visible signature, or none of them"
                raise ValueError(msg)


##### COMPOSE #####
class ComposeIn(msgspec.Struct, frozen=True, kw_only=True):
    """`template`: a name (`invoice`: `<name>.typ` under `<ORGANON_DATA>/doc/templates`, else among the ones shipped) or a path
    to a typst file under the roots. `data`: what the template reads, as JSON."""

    template: str
    data: dict[str, Any] = msgspec.field(default_factory=dict)
