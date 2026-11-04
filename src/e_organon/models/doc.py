"""e_organon.models.doc: what the doc/ tools take and give — files by path, never bytes in the arguments.

Every path is under ORGANON_ROOTS; every file a tool writes lands in ORGANON_OUTBOX (inside a root), named by its
content, so one tool's output is the next one's input."""

from typing import Annotated

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
