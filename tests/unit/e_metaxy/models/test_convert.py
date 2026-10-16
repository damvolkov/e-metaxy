"""tests/unit/e_metaxy/models/convert: the answer shapes the converters hand the edges."""

from e_metaxy.models.convert import DocSection, DocSummary, MarkdownBundle, MarkdownEntry


def test_a_markdown_entry_ships_with_its_notes_empty() -> None:
    entry = MarkdownEntry(name="a.md", markdown="# A", source="html")
    assert (entry.warnings, entry.path, entry.error) == ((), "", "")


def test_a_bundle_holds_many_files_each_with_its_own_error() -> None:
    bundle = MarkdownBundle(
        files=(
            MarkdownEntry(name="a.md", markdown="# A", source="html"),
            MarkdownEntry(name="b.md", markdown="", source="pdf", error="refused"),
        )
    )
    assert [file.name for file in bundle.files] == ["a.md", "b.md"]
    assert bundle.files[1].error == "refused"


def test_a_document_summary_is_its_outline_and_full_text() -> None:
    summary = DocSummary(
        name="filing.pdf",
        pages=4,
        deep=(3, 4),
        markdown="# Filing",
        sections=(DocSection(title="Item 1", level=1, page=1, text="Business"),),
    )
    assert (summary.pages, summary.deep) == (4, (3, 4))
    assert summary.sections[0].title == "Item 1"
