"""tests/unit/e_organon/providers/adapters/barcode: the zxing adapter, open."""

import pytest

from e_organon.providers.adapters.barcode.zxing import ZxingAdapter


@pytest.fixture
async def barcode() -> ZxingAdapter:
    async with ZxingAdapter() as opened:
        return opened
