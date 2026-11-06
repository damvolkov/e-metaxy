"""tests/unit/e_organon/services/image: the image tools over the real OpenCV adapter — a temporary vault for roots, its
outbox inside it, and a photo of a signature placed there."""

from typing import TYPE_CHECKING

import pytest

from e_organon.engines.artifact import ArtifactEngine
from e_organon.providers.adapters.cutout.opencv import OpencvAdapter
from e_organon.providers.adapters.raster.pillow import PillowAdapter
from e_organon.services.files import AllowedFiles
from e_organon.services.image.budget import BudgetImage
from e_organon.services.image.convert import ConvertImageService
from e_organon.services.image.cutout import CutoutImageService
from support.photo import photo
from support.raster import encode, exif_of, quadrants, sample

if TYPE_CHECKING:
    from pathlib import Path

    from support.image import Build, BuildConvert


@pytest.fixture
def pictures(tmp_path: Path) -> Path:
    (tmp_path / "firma.jpg").write_bytes(photo()[0])
    (tmp_path / "underlined.jpg").write_bytes(photo(underline=True)[0])
    (tmp_path / "quadrants.png").write_bytes(sample("PNG"))
    (tmp_path / "turned.jpg").write_bytes(encode(quadrants(), "JPEG", exif=exif_of(6)))
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


@pytest.fixture
def build_convert(pictures: Path) -> BuildConvert:
    """The convert tool over the vault, its pixel budget the given one."""

    def make(max_pixels: int = 1_000_000) -> ConvertImageService:
        raster = PillowAdapter()
        return ConvertImageService(
            raster,
            AllowedFiles((pictures,)),
            ArtifactEngine(pictures / "outbox"),
            BudgetImage(raster, max_pixels=max_pixels),
        )

    return make


@pytest.fixture
def converter(build_convert: BuildConvert) -> ConvertImageService:
    return build_convert()
