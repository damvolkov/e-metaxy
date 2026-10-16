"""e_metaxy.logic.converters: the two processors behind one façade — render a file to Markdown, or read a document.

The single place the service turns bytes into answers, shared by the MCP tools and the REST routes so they
cannot drift. It knows the transport nothing: a caller hands bytes and a name, and gets back the typed
result models. `md` is the fast any-format renderer (a PDF becomes quick context here); `doc` is the deep
reader that routes the hard pages to docling. Errors from the processors (a refusal, an engine failure)
propagate; the edge decides how to surface them."""

from typing import TYPE_CHECKING

from e_metaxy.models.convert import DocSection, DocSummary, MarkdownBundle, MarkdownEntry
from e_metaxy.processors.doc import DocProcessor

if TYPE_CHECKING:
    from e_metaxy.processors.md import MDProcessor
    from e_metaxy.processors.models import Document, MarkdownFile, Section


class Converters:
    """One façade over the Markdown renderer and the deep document reader."""

    __slots__ = ("_doc", "_md")

    def __init__(self, md: MDProcessor, doc: DocProcessor) -> None:
        self._md = md
        self._doc = doc

    ##### PRIVATE — mapping #####

    @staticmethod
    def _entry(file: MarkdownFile) -> MarkdownEntry:
        """A rendered file as the service model, field for field."""
        return MarkdownEntry(
            name=file.name,
            markdown=file.markdown,
            source=file.source,
            warnings=file.warnings,
            path=file.path,
            error=file.error,
        )

    @staticmethod
    def _section(section: Section) -> DocSection:
        """One heading and its body as the service model."""
        return DocSection(title=section.title, level=section.level, page=section.page, text=section.text)

    @classmethod
    def _summary(cls, document: Document) -> DocSummary:
        """A document condensed to what an agent needs: its outline and full text, not every object."""
        return DocSummary(
            name=document.name,
            pages=len(document.pages),
            deep=document.deep,
            markdown=document.markdown,
            sections=tuple(cls._section(section) for section in DocProcessor.sections(document)),
        )

    ############################################################

    ##### PUBLIC #####

    async def markdown(self, data: bytes, *, name: str = "") -> MarkdownBundle:
        """Render any supported file (or a ZIP of them) to Markdown — the fast, any-format path."""
        files = await self._md.convert(data, name=name)
        return MarkdownBundle(files=tuple(self._entry(file) for file in files))

    async def document(self, data: bytes, *, name: str = "") -> DocSummary:
        """Read a document deeply: liteparse everywhere, docling where the page asks for it."""
        return self._summary(await self._doc.process(data, name=name))
