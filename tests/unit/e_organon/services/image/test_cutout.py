"""tests/unit/e_organon/services/image/cutout: image/cutout over the real adapter — four steps then a PNG in the outbox;
an image over the pixel budget is refused before it is decoded, a path outside the roots at the first step."""

import io
from typing import TYPE_CHECKING

import anyio
from PIL import Image

from e_organon.models.doc import FileOut
from e_organon.models.flow import Done, Failed, Step
from e_organon.models.image import CutoutIn

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.image.cutout import CutoutImageService
    from support.image import Build


async def test_cutout_writes_a_transparent_png(cutter: CutoutImageService, pictures: Path) -> None:
    events = [event async for event in cutter.events(CutoutIn(path=str(pictures / "firma.jpg")))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "measure", "cut", "keep"]
    assert isinstance(events[-1], Done)
    out = events[-1].result
    assert isinstance(out, FileOut)
    image = Image.open(io.BytesIO(await anyio.Path(out.path).read_bytes()))
    assert (image.format, image.mode, out.path.startswith(str(pictures / "outbox" / "firma-cutout-"))) == (
        "PNG",
        "RGBA",
        True,
    )
    assert out.size == len(await anyio.Path(out.path).read_bytes())


async def test_cutout_options_reach_the_adapter(cutter: CutoutImageService, pictures: Path) -> None:
    whole = [e async for e in cutter.events(CutoutIn(path=str(pictures / "firma.jpg"), crop=False, color=False))][-1]
    assert isinstance(whole, Done)
    assert Image.open(io.BytesIO(await anyio.Path(whole.result.path).read_bytes())).size == (600, 300)


async def test_cutout_refuses_a_huge_image_before_decoding(pictures: Path, build: Build) -> None:
    events = [event async for event in build(max_pixels=1000).events(CutoutIn(path=str(pictures / "firma.jpg")))]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, "180000" in events[-1].reason) == ("ImageTooLargeError", True)


async def test_cutout_refuses_outside_the_roots(cutter: CutoutImageService) -> None:
    events = [event async for event in cutter.events(CutoutIn(path="/etc/hostname"))]
    assert events[0] == Step(name="resolve", index=0, total=4)
    assert events[1:] == [Failed(kind="OutsideRootsError", reason=getattr(events[1], "reason", ""))]
