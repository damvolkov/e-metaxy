"""providers/adapters/cutout/opencv: ink lifted off a photographed sheet with OpenCV and scikit-image, in process.

The method won the bench against rembg's ISNet (`docs/bench/cutout.md`): the photo's grey is divided by a morphological
closing of itself (the sheet's tint, the uneven light and shadows flatten to white), ink is what Sauvola's local
threshold and an absolute darkness gate both call dark, and connected specks under `SPECK` pixels are dropped. The alpha is
soft: inside the ink dilated by one pixel it is the darkness of the flattened grey, never below the mask's own 255, so
edges are anti-aliased and strokes solid. `size` reads the header with Pillow — lazily, no pixel decoded — so a caller can
refuse a huge image before `cut` decodes it. Everything runs off the loop, in a worker thread: OpenCV and NumPy release
the GIL."""

import io
from typing import ClassVar, Final, Self

import anyio
import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from skimage.filters import threshold_sauvola

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

### the bench's parameters, fixed on its dev set: Sauvola's window and k, the darkness gate (0-255), the smallest kept
### speck (pixels) and the closing's diameter.
WINDOW, K, GATE, SPECK, CLOSE = 25, 0.2, 150, 30, 31
### transparent pixels kept around the ink when cropping.
PADDING: Final[int] = 8
### a flattened grey's darkness becomes alpha twice as fast: half-dark is already opaque.
SLOPE: Final[int] = 2


##### ADAPTER #####
class OpencvAdapter:
    """Ink cut-out; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("opencv", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

    ##### PRIVATE #####

    @staticmethod
    def _size_read(data: bytes) -> tuple[int, int]:
        try:
            with Image.open(io.BytesIO(data)) as image:
                return image.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error

    @staticmethod
    def _cut_ink(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The flattened grey and the ink's mask (bool) of a BGR photo."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        background = cv2.morphologyEx(
            gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE, CLOSE))
        )
        flat = np.clip(gray.astype(np.float32) / np.maximum(background, 1) * 255, 0, 255)
        ink = (flat < threshold_sauvola(flat, window_size=WINDOW, k=K)) & (flat < GATE)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
        keep = np.zeros(count, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= SPECK
        return flat, keep[labels]

    @staticmethod
    def _cut_crop(rgba: np.ndarray) -> np.ndarray:
        """The sheet cut to the opaque pixels' box, `PADDING` clear pixels around."""
        ys, xs = np.nonzero(rgba[..., 3])
        top, left = max(ys.min() - PADDING, 0), max(xs.min() - PADDING, 0)
        return rgba[top : ys.max() + PADDING + 1, left : xs.max() + PADDING + 1]

    def _cut_run(self, data: bytes, *, color: bool, crop: bool) -> bytes:
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        match image:
            case None:
                msg = "not a readable image: no decoder took it"
                raise ParseError(msg)
        flat, ink = self._cut_ink(image)
        match bool(ink.any()):
            case False:
                msg = "no ink found: the sheet is clear"
                raise ParseError(msg)
        near = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        alpha = np.where(near, np.clip((255 - flat) * SLOPE, 0, 255), 0).astype(np.uint8)
        alpha[ink] = 255
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if color else np.zeros_like(image)
        rgba = np.dstack([rgb, alpha])
        _, png = cv2.imencode(".png", cv2.cvtColor(self._cut_crop(rgba) if crop else rgba, cv2.COLOR_RGBA2BGRA))
        return png.tobytes()

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def size(self, data: bytes) -> tuple[int, int]:
        return await anyio.to_thread.run_sync(self._size_read, data)

    async def cut(self, data: bytes, *, color: bool, crop: bool) -> bytes:
        return await anyio.to_thread.run_sync(lambda: self._cut_run(data, color=color, crop=crop))
