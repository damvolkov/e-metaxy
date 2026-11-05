"""tests/unit/e_organon/providers/adapters/cutout/opencv: a photo of ink cut out as a transparent PNG — the paper's tint and
the uneven light gone, the ink's own colour kept, the sheet cropped to the ink."""

import io

import numpy as np
import pytest
from PIL import Image

from e_organon.infra.errors import ParseError
from e_organon.providers.adapters.cutout.opencv import PADDING, WINDOW, K, OpencvAdapter
from support.photo import INK, H, W, photo


@pytest.fixture
async def cutout() -> OpencvAdapter:
    async with OpencvAdapter() as opened:
        return opened


def rgba(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


async def test_opencv_health(cutout: OpencvAdapter) -> None:
    assert await cutout.health()


async def test_opencv_size_reads_the_header(cutout: OpencvAdapter) -> None:
    data, _ = photo()
    assert await cutout.size(data) == (W, H)


async def test_opencv_cuts_the_ink_as_the_mask_says(cutout: OpencvAdapter) -> None:
    data, mask = photo()
    out = rgba(await cutout.cut(data, color=True, crop=False))
    found, truth = out[..., 3] > 200, mask > 127
    iou = (found & truth).sum() / (found | truth).sum()
    assert (out.shape[:2], iou > 0.8) == ((H, W), True)


async def test_opencv_printed_lines_darker_than_the_gate_are_no_ink(cutout: OpencvAdapter) -> None:
    data, mask = photo(lined=True)
    out = rgba(await cutout.cut(data, color=True, crop=False))
    found, truth = out[..., 3] > 200, mask > 127
    iou = (found & truth).sum() / (found | truth).sum()
    ### the vertical line and the stretch of the tilted one left of the strokes hold no ink at all.
    assert (iou > 0.8, int(found[:, 55:66].sum()), int(found[160:185, 45:100].sum())) == (True, 0, 0)


async def test_opencv_a_lined_sheet_and_a_clear_one_give_the_same_ink(cutout: OpencvAdapter) -> None:
    ### the lines subtracted leave the strokes as the line-free photo's, give or take a crossing's bridge.
    lined = rgba(await cutout.cut(photo(lined=True)[0], color=True, crop=False))[..., 3] > 200
    clear = rgba(await cutout.cut(photo()[0], color=True, crop=False))[..., 3] > 200
    assert (lined & clear).sum() / (lined | clear).sum() > 0.85


async def test_opencv_keeps_the_inks_colour_or_makes_it_black(cutout: OpencvAdapter) -> None:
    data, _ = photo()
    kept = rgba(await cutout.cut(data, color=True, crop=False))
    black = rgba(await cutout.cut(data, color=False, crop=False))
    solid = kept[..., 3] == 255
    blue = kept[solid][:, :3].mean(axis=0)
    assert (blue[2] > blue[0], tuple(black[black[..., 3] > 0][:, :3].max(axis=0))) == (True, (0, 0, 0))
    assert abs(float(blue[2]) - INK[0]) < 90


async def test_opencv_crops_to_the_ink_with_a_margin(cutout: OpencvAdapter) -> None:
    data, mask = photo()
    out = rgba(await cutout.cut(data, color=True, crop=True))
    ys, xs = np.nonzero(mask)
    ### the ink's box plus the margin on each side, give or take the soft edge.
    assert abs(out.shape[0] - (ys.max() - ys.min() + 1 + 2 * PADDING)) <= 4
    assert abs(out.shape[1] - (xs.max() - xs.min() + 1 + 2 * PADDING)) <= 4
    assert out[0, 0, 3] == 0


async def test_opencv_a_sheet_without_ink_is_refused(cutout: OpencvAdapter) -> None:
    blank = io.BytesIO()
    Image.new("RGB", (200, 100), (235, 235, 235)).save(blank, format="PNG")
    with pytest.raises(ParseError, match="no ink"):
        await cutout.cut(blank.getvalue(), color=True, crop=True)


async def test_opencv_size_of_what_is_not_an_image_is_refused(cutout: OpencvAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await cutout.size(b"hello")


async def test_opencv_cut_of_what_is_not_an_image_is_refused(cutout: OpencvAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await cutout.cut(b"hello", color=True, crop=True)


async def test_opencv_sauvola_is_the_definition_with_reflected_borders() -> None:
    """The port of scikit-image's threshold, against the formula spelled out over `numpy`'s own reflect padding: the
    window's mean and deviation, `m * (1 + k * (s / R - 1))`, R = 1 as scikit-image sets it for a float image."""
    rng = np.random.default_rng(3)
    flat = rng.uniform(0, 255, (40, 50)).astype(np.float32)
    half = WINDOW // 2
    windows = np.lib.stride_tricks.sliding_window_view(
        np.pad(flat.astype(np.float64), half, mode="reflect"), (WINDOW, WINDOW)
    )
    mean, deviation = windows.mean(axis=(2, 3)), windows.std(axis=(2, 3))
    expected = mean * (1 + K * (deviation / 1.0 - 1))
    assert np.allclose(OpencvAdapter._cut_sauvola(flat), expected, rtol=1e-9)
