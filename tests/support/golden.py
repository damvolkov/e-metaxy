"""tests/support/golden: the goldens' inputs, made once and kept in `tests/resources/golden/` — `python -m support.golden` rewrites
them: a photo of a signature (JPEG), the mask its ink should leave (the adapter's own alpha at 128 and up, as 255/0, the day
the method was accepted), and a one-page contract with `Firma:` on it."""

import io
from pathlib import Path

import anyio
import numpy as np
from PIL import Image

from e_organon.providers.adapters.cutout.opencv import OpencvAdapter
from support.pdf import labelled
from support.photo import photo

HERE = Path(__file__).resolve().parents[1] / "resources" / "golden"


def build(target: Path = HERE) -> None:

    target.mkdir(parents=True, exist_ok=True)
    jpg = photo()[0]
    (target / "signature.jpg").write_bytes(jpg)
    cut = anyio.run(lambda: OpencvAdapter().cut(jpg, color=True, crop=False))
    alpha = np.asarray(Image.open(io.BytesIO(cut)).convert("RGBA"))[..., 3]
    Image.fromarray(((alpha >= 128) * 255).astype(np.uint8)).save(target / "signature.mask.png")
    (target / "contract.pdf").write_bytes(labelled(second=False))


if __name__ == "__main__":
    build()
