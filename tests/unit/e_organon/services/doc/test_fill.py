"""tests/unit/e_organon/services/doc/fill: a filled copy kept in the outbox, the original untouched."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FillIn
from e_organon.services.doc.fill import FillDocService

if TYPE_CHECKING:
    from pathlib import Path


async def test_fill_keeps_a_filled_copy(pdf, files, artifacts, vault: Path) -> None:
    original = (vault / "form.pdf").read_bytes()
    out = await FillDocService(pdf, files, artifacts).run(
        FillIn(path=str(vault / "form.pdf"), values={"persona.nombre": "Ana"})
    )
    filled = (vault / "outbox" / out.path.rsplit("/", 1)[-1]).read_bytes()
    values = {field.name: field.value for field in (await pdf.info(filled)).fields}
    assert (values["persona.nombre"], (vault / "form.pdf").read_bytes() == original) == ("Ana", True)
