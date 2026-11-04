"""tests/unit/e_organon/services/doc/inspect: a PDF's pages, metadata and fields, in two steps."""

from typing import TYPE_CHECKING

from e_organon.models.doc import InspectIn
from e_organon.services.doc.inspect import InspectDocService

if TYPE_CHECKING:
    from pathlib import Path


async def test_inspect_lists_the_fields(pdf, files, vault: Path) -> None:
    out = await InspectDocService(pdf, files).run(InspectIn(path=str(vault / "form.pdf")))
    assert (out.name, len(out.pages), out.metadata["Title"], len(out.fields)) == ("form.pdf", 1, "Solicitud", 6)
