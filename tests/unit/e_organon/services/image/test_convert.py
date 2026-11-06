"""tests/unit/e_organon/services/image/convert: image/convert over the real adapter — four steps then the image in the outbox,
named by its content and its format; an image over the pixel budget is refused before it is decoded, a path outside the roots
at the first step."""

from typing import TYPE_CHECKING

import anyio

from e_organon.models.doc import FileOut
from e_organon.models.flow import Done, Failed, Step
from e_organon.models.image import ConvertIn
from e_organon.ports.raster import RasterFormat
from support.raster import H, W, opened

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.image.convert import ConvertImageService
    from support.image import BuildConvert


async def test_convert_writes_the_image_in_the_outbox(converter: ConvertImageService, pictures: Path) -> None:
    order = ConvertIn(path=str(pictures / "quadrants.png"), format=RasterFormat.WEBP, width=60)
    events = [event async for event in converter.events(order)]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "measure", "convert", "keep"]
    assert isinstance(events[-1], Done)
    out = events[-1].result
    assert isinstance(out, FileOut)
    written = await anyio.Path(out.path).read_bytes()
    assert (
        opened(written).format,
        opened(written).size,
        out.path.startswith(str(pictures / "outbox" / "quadrants-convert-")),
        out.path.endswith(".webp"),
        out.size,
    ) == ("WEBP", (60, 40), True, True, len(written))


async def test_convert_without_a_format_keeps_the_sources_suffix(
    converter: ConvertImageService, pictures: Path
) -> None:
    done = [e async for e in converter.events(ConvertIn(path=str(pictures / "turned.jpg")))][-1]
    assert isinstance(done, Done)
    assert (done.result.path.endswith(".jpg"), opened(await anyio.Path(done.result.path).read_bytes()).size) == (
        True,
        (H, W),
    )


async def test_convert_twice_is_the_same_file(converter: ConvertImageService, pictures: Path) -> None:
    order = ConvertIn(path=str(pictures / "turned.jpg"), format=RasterFormat.AVIF, width=40)
    first, second = [[e async for e in converter.events(order)][-1] for _ in range(2)]
    assert isinstance(first, Done)
    assert first == second


async def test_convert_refuses_a_huge_image_before_decoding(pictures: Path, build_convert: BuildConvert) -> None:
    events = [e async for e in build_convert(max_pixels=1000).events(ConvertIn(path=str(pictures / "quadrants.png")))]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, "9600" in events[-1].reason) == ("ImageTooLargeError", True)


async def test_convert_refuses_outside_the_roots(converter: ConvertImageService) -> None:
    events = [event async for event in converter.events(ConvertIn(path="/etc/hostname"))]
    assert events[0] == Step(name="resolve", index=0, total=4)
    assert events[1:] == [Failed(kind="OutsideRootsError", reason=getattr(events[1], "reason", ""))]


async def test_convert_a_file_that_is_no_image_fails_with_a_parse_error(
    converter: ConvertImageService, pictures: Path
) -> None:
    (pictures / "text.png").write_text("not an image")
    events = [event async for event in converter.events(ConvertIn(path=str(pictures / "text.png")))]
    assert (events[-1].kind, "not a readable image" in events[-1].reason) == ("ParseError", True)  # ty: ignore[unresolved-attribute]
