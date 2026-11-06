"""tests/unit/e_organon/providers/adapters/raster/pillow: an image read, reshaped and written — each step of the spec told by a
pixel of the four-quadrant picture (red, green / blue, yellow), the bytes by their decoded format."""

from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageCms

from e_organon.infra.errors import ParseError
from e_organon.ports.raster import RasterFit, RasterFormat, RasterSpec
from support.raster import BLUE, GREEN, RED, YELLOW, H, W, Write, alpha, encode, near, opened, quadrants, rgb, sample

if TYPE_CHECKING:
    from e_organon.providers.adapters.raster.pillow import PillowAdapter


async def test_pillow_health(raster: PillowAdapter) -> None:
    assert await raster.health()


async def test_pillow_size_reads_the_header(raster: PillowAdapter, png: bytes) -> None:
    assert await raster.size(png) == (W, H)


async def test_pillow_size_of_no_image_is_a_parse_error(raster: PillowAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await raster.size(b"nope")


@pytest.mark.parametrize("codec", list(RasterFormat))
async def test_pillow_writes_every_format(write: Write, png: bytes, codec: RasterFormat) -> None:
    image = opened(await write(png, RasterSpec(format=codec)))
    assert (image.format, image.size) == (codec.name, (W, H))


async def test_pillow_without_a_format_keeps_the_sources(write: Write) -> None:
    image = opened(await write(sample("WEBP"), RasterSpec()))
    assert image.format == "WEBP"


async def test_pillow_without_a_format_writes_png_when_the_source_cannot_be_written(write: Write) -> None:
    assert opened(await write(sample("GIF", mode="P"), RasterSpec())).format == "PNG"


@pytest.mark.parametrize("codec", list(RasterFormat))
async def test_pillow_same_input_same_bytes(write: Write, png: bytes, codec: RasterFormat) -> None:
    spec = RasterSpec(format=codec, width=60)
    assert await write(png, spec) == await write(png, spec)


@pytest.mark.parametrize(
    ("spec", "size"),
    [
        (RasterSpec(width=60), (60, 40)),
        (RasterSpec(height=20), (30, 20)),
        (RasterSpec(width=50, height=50), (50, 33)),
        (RasterSpec(width=500), (W, H)),
        (RasterSpec(width=50, height=50, fit=RasterFit.COVER), (50, 50)),
        (RasterSpec(width=50, height=50, fit=RasterFit.STRETCH), (50, 50)),
        (RasterSpec(width=30, fit=RasterFit.COVER), (30, 80)),
        (RasterSpec(fit=RasterFit.STRETCH), (W, H)),
    ],
    ids=["width", "height", "box", "never-enlarged", "cover", "stretch", "cover-one-side", "stretch-no-box"],
)
async def test_pillow_resize(write: Write, png: bytes, spec: RasterSpec, size: tuple[int, int]) -> None:
    assert opened(await write(png, spec)).size == size


async def test_pillow_crop_is_in_source_pixels(write: Write, png: bytes) -> None:
    image = opened(await write(png, RasterSpec(crop=(60, 40, 120, 80))))
    assert (image.size, rgb(image, (5, 5))) == ((60, 40), YELLOW)


@pytest.mark.parametrize("crop", [(10, 10, 10, 20), (0, 0, 500, 10), (-1, 0, 10, 10), (30, 0, 10, 10)])
async def test_pillow_crop_outside_the_picture_is_a_parse_error(
    write: Write, png: bytes, crop: tuple[int, int, int, int]
) -> None:
    with pytest.raises(ParseError, match="crop"):
        await write(png, RasterSpec(crop=crop))


@pytest.mark.parametrize(
    ("degrees", "size", "corner"),
    [(90, (H, W), BLUE), (180, (W, H), YELLOW), (270, (H, W), GREEN)],
    ids=["quarter", "half", "three-quarters"],
)
async def test_pillow_rotates_clockwise(
    write: Write, png: bytes, degrees: int, size: tuple[int, int], corner: tuple[int, int, int]
) -> None:
    image = opened(await write(png, RasterSpec(rotate=degrees)))  # ty: ignore[invalid-argument-type]
    assert (image.size, rgb(image, (3, 3))) == (size, corner)


async def test_pillow_applies_the_exif_orientation_first(write: Write, jpeg_turned: bytes) -> None:
    image = opened(await write(jpeg_turned, RasterSpec(format=RasterFormat.PNG)))
    assert (image.size, near(rgb(image, (3, 3)), BLUE)) == ((H, W), True)


async def test_pillow_strips_metadata_unless_asked_to_keep(write: Write, jpeg_turned: bytes) -> None:
    stripped = opened(await write(jpeg_turned, RasterSpec()))
    kept = opened(await write(jpeg_turned, RasterSpec(keep=True)))
    assert (dict(stripped.getexif()), kept.getexif().get(0x013B)) == ({}, "ana")


async def test_pillow_srgb_takes_a_wide_gamut_picture_into_srgb(write: Write, p3_jpeg: bytes) -> None:
    source, plain = opened(p3_jpeg).convert("RGB"), opened(await write(p3_jpeg, RasterSpec(srgb=False)))
    out = opened(await write(p3_jpeg, RasterSpec()))
    pixel = (30, 20)
    assert (
        out.info.get("icc_profile"),
        rgb(plain, pixel) == rgb(source, pixel),
        max(abs(a - b) for a, b in zip(rgb(out, pixel), rgb(source, pixel), strict=True)) > 8,
    ) == (None, True, True)


async def test_pillow_an_srgb_profile_is_left_alone(write: Write) -> None:
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    data = encode(quadrants(), "PNG", icc_profile=srgb)
    assert near(opened(await write(data, RasterSpec())).convert("RGB").getpixel((3, 3)), RED, 3)


async def test_pillow_keep_leaves_the_profile(write: Write, p3_jpeg: bytes) -> None:
    out = opened(await write(p3_jpeg, RasterSpec(keep=True, srgb=False)))
    assert out.info.get("icc_profile") is not None


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
async def test_pillow_jpeg_has_no_transparency_it_is_flattened_on_white(write: Write, mode: str) -> None:
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0)).convert(mode)
    out = opened(
        await write(
            encode(image, "PNG", transparency=0) if mode == "P" else encode(image, "PNG"),
            RasterSpec(format=RasterFormat.JPEG),
        )
    )
    assert near(rgb(out, (5, 5)), (255, 255, 255), 6)


async def test_pillow_png_keeps_transparency(write: Write) -> None:
    data = encode(Image.new("RGBA", (W, H), (10, 20, 30, 0)), "PNG")
    assert alpha(opened(await write(data, RasterSpec(format=RasterFormat.WEBP))), (5, 5)) == 0


async def test_pillow_cmyk_becomes_rgb(write: Write) -> None:
    data = encode(quadrants().convert("CMYK"), "JPEG")
    assert opened(await write(data, RasterSpec(format=RasterFormat.PNG))).mode == "RGB"


async def test_pillow_sixteen_bits_become_eight(write: Write) -> None:
    image = Image.new("I;16", (W, H), 65535)
    out = opened(await write(encode(image, "PNG"), RasterSpec(format=RasterFormat.JPEG)))
    assert (out.mode, out.getpixel((5, 5))) == ("L", 255)


async def test_pillow_a_gray_picture_stays_gray(write: Write) -> None:
    assert opened(await write(encode(quadrants(mode="L"), "PNG"), RasterSpec())).mode == "L"


async def test_pillow_an_animation_is_its_first_frame(write: Write) -> None:
    first, second = quadrants(), quadrants().rotate(90, expand=True).resize((W, H))
    gif = encode(first.convert("P"), "GIF", save_all=True, append_images=[second.convert("P")])
    assert near(opened(await write(gif, RasterSpec(format=RasterFormat.PNG))).convert("RGB").getpixel((3, 3)), RED)


async def test_pillow_no_image_is_a_parse_error(write: Write) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await write(b"\x89PNG not really", RasterSpec())


async def test_pillow_a_truncated_image_is_a_parse_error(write: Write, png: bytes) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await write(png[: len(png) // 2], RasterSpec())


@pytest.mark.parametrize(("width", "size"), [(15, (15, 10)), (40, (40, 27)), (60, (60, 40)), (500, (W, H))])
async def test_pillow_jpeg_resize_is_the_box_whatever_the_shrink_on_load(
    write: Write, width: int, size: tuple[int, int]
) -> None:
    assert opened(await write(sample("JPEG"), RasterSpec(width=width))).size == size
