"""tests/unit/e_organon/services/doc/split: page ranges kept as their own PDFs, named by range."""

from typing import TYPE_CHECKING

from e_organon.models.doc import SplitIn
from e_organon.services.doc.split import SplitDocService

if TYPE_CHECKING:
    from pathlib import Path


async def test_split_keeps_one_pdf_per_range(pdf, files, artifacts, vault: Path) -> None:
    out = await SplitDocService(pdf, files, artifacts).run(
        SplitIn(path=str(vault / "three.pdf"), ranges=[(0, 0), (1, 2)])
    )
    names = [file.path.rsplit("/", 1)[-1] for file in out.files]
    assert [name.split("-")[1:3] for name in names] == [["p0", "0"], ["p1", "2"]]
