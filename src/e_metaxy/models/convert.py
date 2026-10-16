"""e_metaxy.models.convert: what the converters hand a caller — the Markdown a file became, or a document read.

`MarkdownBundle` is one file rendered (a ZIP arrives as many `MarkdownEntry`); `DocSummary` is the condensed
reading of `DocProcessor` — the whole document's markdown and its sections, not every table and picture,
which is what an agent needs in context and what both the MCP tool and the REST route return verbatim."""

from e_metaxy.core.struct import CheckedStruct


##### MARKDOWN #####
class MarkdownEntry(CheckedStruct, frozen=True, kw_only=True):
    """One file rendered: its shipping name, the Markdown, the format read from and the engine, plus notes."""

    name: str
    markdown: str
    source: str
    warnings: tuple[str, ...] = ()
    path: str = ""
    error: str = ""


class MarkdownBundle(CheckedStruct, frozen=True, kw_only=True):
    """The result of converting one input: the files it produced — one, or many for a ZIP."""

    files: tuple[MarkdownEntry, ...]


##### DOCUMENT #####
class DocSection(CheckedStruct, frozen=True, kw_only=True):
    """One heading of a document with the body text beneath it, up to the next heading."""

    title: str
    level: int
    page: int
    text: str


class DocSummary(CheckedStruct, frozen=True, kw_only=True):
    """A document read by the deep engine: how it came back (pages, which were read deeply), its whole
    Markdown, and its sections. Tables and pictures stay server-side; an agent reads the text and outline."""

    name: str
    pages: int
    deep: tuple[int, ...]
    markdown: str
    sections: tuple[DocSection, ...]
