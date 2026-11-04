"""tests/unit/e_organon/services/doc: the doc tools over the real in-process adapters — a temporary vault for roots, its
outbox inside it, and a form and a blank PDF placed there."""

from typing import TYPE_CHECKING

import pytest

from e_organon.engines.artifact import ArtifactEngine
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from e_organon.services.files import AllowedFiles
from support.pdf import blank, form

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "form.pdf").write_bytes(form())
    (tmp_path / "three.pdf").write_bytes(blank(3))
    return tmp_path


@pytest.fixture
def files(vault: Path) -> AllowedFiles:
    return AllowedFiles((vault,))


@pytest.fixture
def artifacts(vault: Path) -> ArtifactEngine:
    return ArtifactEngine(vault / "outbox")


@pytest.fixture
def pdf() -> PikepdfAdapter:
    return PikepdfAdapter()


@pytest.fixture
def render() -> PdfiumAdapter:
    return PdfiumAdapter()
