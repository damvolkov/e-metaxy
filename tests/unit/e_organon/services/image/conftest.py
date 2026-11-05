"""tests/unit/e_organon/services/image: the image tools over the real OpenCV adapter — a temporary vault for roots, its
outbox inside it, and a photo of a signature placed there."""

from typing import TYPE_CHECKING

import pytest

from e_organon.engines.artifact import ArtifactEngine
from e_organon.providers.adapters.cutout.opencv import OpencvAdapter
from e_organon.services.files import AllowedFiles
from e_organon.services.image.cutout import CutoutImageService
from support.photo import photo

if TYPE_CHECKING:
    from pathlib import Path

    from support.image import Build


@pytest.fixture
def pictures(tmp_path: Path) -> Path:
    (tmp_path / "firma.jpg").write_bytes(photo()[0])
    return tmp_path


@pytest.fixture
def build(pictures: Path) -> Build:
    """The cut-out tool over the vault, its pixel budget the given one."""

    def make(max_pixels: int = 1_000_000) -> CutoutImageService:
        return CutoutImageService(
            OpencvAdapter(), AllowedFiles((pictures,)), ArtifactEngine(pictures / "outbox"), max_pixels=max_pixels
        )

    return make


@pytest.fixture
def cutter(build: Build) -> CutoutImageService:
    return build()
