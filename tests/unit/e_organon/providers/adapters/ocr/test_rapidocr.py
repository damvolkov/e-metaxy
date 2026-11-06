"""tests/unit/e_organon/providers/adapters/ocr/rapidocr: words and boxes off a rendered line of text with the real engine
(slow: its models are fetched on the first open), and what the adapter refuses without it."""

from pathlib import Path

import anyio
import pytest

from e_organon.infra.errors import ParseError, ProviderError
from e_organon.providers.adapters.ocr.rapidocr import RapidocrAdapter
from support.ink import text_png


@pytest.mark.slow
async def test_rapidocr_reads_the_words_with_their_boxes(engine: RapidocrAdapter) -> None:
    words = await engine.read(text_png(), "spa")
    ### the engine may cut a long word in two (`núm` `ero`): the letters are what is held, not the cuts.
    assert "".join(word.text for word in words) == "Lafacturanúmero42estápagada."
    ### left to right on one line, each box inside the image around the text's start (20, 20).
    lefts = [word.box[0] for word in words]
    assert (lefts == sorted(lefts), all(0 < word.box[1] < 60 and word.box[3] < 100 for word in words)) == (True, True)


@pytest.mark.slow
async def test_rapidocr_a_blank_image_has_no_words(engine: RapidocrAdapter) -> None:
    assert await engine.read(text_png(""), "") == ()


@pytest.mark.slow
async def test_rapidocr_models_are_kept_where_it_was_told(engine: RapidocrAdapter, models: Path) -> None:
    assert sorted([path.suffix async for path in anyio.Path(models).iterdir()]) == [".onnx"] * 3
    assert await engine.health()


async def test_rapidocr_size_reads_the_header() -> None:
    assert await RapidocrAdapter(models=Path("unused")).size(text_png()) == (900, 120)


async def test_rapidocr_what_is_no_image_is_refused() -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await RapidocrAdapter(models=Path("unused")).size(b"hello")


async def test_rapidocr_unopened_it_is_refused() -> None:
    adapter = RapidocrAdapter(models=Path("unused"))
    with pytest.raises(ProviderError, match="not open"):
        await adapter.read(text_png(), "")
    assert not await adapter.health()
