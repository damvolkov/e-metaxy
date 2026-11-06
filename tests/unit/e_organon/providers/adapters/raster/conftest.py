"""tests/unit/e_organon/providers/adapters/raster: the Pillow adapter, open, and the images it is given."""

from typing import TYPE_CHECKING

import pytest

from e_organon.providers.adapters.raster.pillow import PillowAdapter
from support.raster import H, W, encode, exif_of, quadrants, sample, wide_gamut

if TYPE_CHECKING:
    from e_organon.ports.raster import RasterSpec
    from support.raster import Write


@pytest.fixture
async def raster() -> PillowAdapter:
    async with PillowAdapter() as opened:
        return opened


@pytest.fixture
def write(raster: PillowAdapter) -> Write:
    """An image converted, its bytes."""

    async def run(data: bytes, spec: RasterSpec) -> bytes:
        return (await raster.convert(data, spec)).data

    return run


@pytest.fixture
def png() -> bytes:
    return sample("PNG")


@pytest.fixture
def jpeg_turned() -> bytes:
    """Stored 120 x 80, EXIF orientation 6: shown 80 x 120, the stored top-left (red) at the top-right."""
    return encode(quadrants(), "JPEG", exif=exif_of(6))


@pytest.fixture
def p3_jpeg() -> bytes:
    return encode(quadrants((W, H)).point(lambda v: v * 200 // 255), "JPEG", icc_profile=wide_gamut(), quality=95)
