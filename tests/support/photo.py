"""tests/support/photo: a phone photo of a signature, made small — blue-black strokes with a known mask, on tinted paper
lit unevenly, a lighter printed form line under them, blurred and JPEG-compressed: the bench's generator, cut down."""

import cv2
import numpy as np

W, H = 600, 300
### the ink, BGR: a blue pen.
INK: tuple[int, int, int] = (120, 40, 20)


def strokes() -> np.ndarray:
    """The ink mask (0/255): three smooth curves a few pixels wide, in the middle of the sheet."""
    mask = np.zeros((H, W), np.uint8)
    t = np.linspace(0, 1, 200)
    for shift, width in ((0, 3), (25, 2), (-30, 4)):
        x = 120 + 360 * t
        y = H / 2 + shift + 45 * np.sin(t * 9 + shift / 10) * (1 - t)
        pts = np.stack([x, y], 1).astype(np.int32)
        cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=width, lineType=cv2.LINE_AA)
    return mask


def photo() -> tuple[bytes, np.ndarray]:
    """The JPEG bytes of the photo, and the exact mask of its ink."""
    rng = np.random.default_rng(7)
    mask = strokes()
    paper = np.array([215, 232, 240], np.float32)
    img = np.ones((H, W, 3), np.float32) * paper + rng.normal(0, 3, (H, W, 3))
    cv2.line(img, (40, 250), (W - 40, 250), tuple(float(v) for v in paper * 0.7), 2)
    alpha = (mask.astype(np.float32) / 255)[..., None] * 0.9
    img = img * (1 - alpha) + np.array(INK, np.float32) * alpha
    gx, gy = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
    img = np.clip(img * (1 - 0.35 * (0.6 * gx + 0.4 * gy))[..., None], 0, 255).astype(np.uint8)
    _, jpg = cv2.imencode(".jpg", cv2.GaussianBlur(img, (0, 0), 0.7), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return jpg.tobytes(), mask
