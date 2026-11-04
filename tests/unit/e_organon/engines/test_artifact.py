"""tests/unit/e_organon/engines/artifact: an output kept by its content — the same bytes, the same path, written once."""

from typing import TYPE_CHECKING

from e_organon.engines.artifact import ArtifactEngine

if TYPE_CHECKING:
    from pathlib import Path


async def test_artifact_keeps_by_content(tmp_path: Path) -> None:
    engine = ArtifactEngine(tmp_path / "outbox")
    first = await engine.keep(b"pdf", "report", ".pdf")
    again = await engine.keep(b"pdf", "report", ".pdf")
    other = await engine.keep(b"other", "report", ".pdf")
    assert (first == again, first != other, first.read_bytes(), first.name.startswith("report-")) == (
        True,
        True,
        b"pdf",
        True,
    )
