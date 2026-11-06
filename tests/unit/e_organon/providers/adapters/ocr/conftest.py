"""tests/unit/e_organon/providers/adapters/ocr: the real engine, opened once for the run on models fetched into a directory of
the run's own (a slow test: the first open downloads them)."""

from typing import TYPE_CHECKING

import pytest

from e_organon.providers.adapters.ocr.rapidocr import RapidocrAdapter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture(scope="session")
def models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("rapidocr-models")


@pytest.fixture
async def engine(models: Path) -> AsyncIterator[RapidocrAdapter]:
    async with RapidocrAdapter(models=models) as opened:
        yield opened
