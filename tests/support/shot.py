"""tests/support/shot: a PDF's first page as pdfium displays it — rotation and crop box applied — as an RGB array, 72 dpi, one
pixel a point: what a stamp's position is checked against, with none of the code that placed it."""

import numpy as np
import pypdfium2 as pdfium


def shot(data: bytes) -> np.ndarray:
    """The displayed page, rows from the top: `(height, width, 3)` uint8."""
    return np.asarray(pdfium.PdfDocument(data)[0].render(scale=1).to_pil().convert("RGB"))


def box_of(mask: np.ndarray) -> tuple[int, int, int, int]:
    """The `(left, top, right, bottom)` pixel box of what `mask` marks."""
    rows, cols = np.nonzero(mask)
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def reddish(page: np.ndarray) -> np.ndarray:
    return (page[..., 0] > 200) & (page[..., 1] < 60) & (page[..., 2] < 60)


def dark(page: np.ndarray) -> np.ndarray:
    return page.max(axis=2) < 110
