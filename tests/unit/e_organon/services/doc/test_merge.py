"""tests/unit/e_organon/services/doc/merge: PDFs joined, the result kept in the outbox."""

from typing import TYPE_CHECKING

from e_organon.models.doc import MergeIn
from e_organon.services.doc.merge import MergeDocService

if TYPE_CHECKING:
    from pathlib import Path


async def test_merge_keeps_one_pdf(pdf, files, artifacts, vault: Path) -> None:
    paths = [str(vault / "three.pdf"), str(vault / "form.pdf")]
    out = await MergeDocService(pdf, files, artifacts).run(MergeIn(paths=paths, name="pack"))
    kept = vault / "outbox" / out.path.rsplit("/", 1)[-1]
    assert (kept.name.startswith("pack-"), len((await pdf.info(kept.read_bytes())).pages)) == (True, 4)
