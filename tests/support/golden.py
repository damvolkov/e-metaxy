"""tests/support/golden: the goldens' inputs, made once and kept in `tests/resources/golden/` — `python -m support.golden` rewrites
them: a photo of a signature (JPEG), the mask its ink should leave (the adapter's own alpha at 128 and up, as 255/0, the day
the method was accepted), and a one-page contract with `Firma:` on it, and the text of the shipped invoice over `invoice.json`."""

import io
import json
from pathlib import Path

import anyio
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from e_organon.api.lifespan.services import TEMPLATES as SHIPPED
from e_organon.providers.adapters.compose.typst import TypstAdapter
from e_organon.providers.adapters.cutout.opencv import OpencvAdapter
from support.pdf import labelled
from support.photo import photo

HERE = Path(__file__).resolve().parents[1] / "resources" / "golden"


def build(target: Path = HERE) -> None:

    target.mkdir(parents=True, exist_ok=True)
    jpg = photo()[0]
    (target / "signature.jpg").write_bytes(jpg)
    cut = anyio.run(lambda: OpencvAdapter().cut(jpg, color=True, crop=False, lines=True))
    alpha = np.asarray(Image.open(io.BytesIO(cut)).convert("RGBA"))[..., 3]
    Image.fromarray(((alpha >= 128) * 255).astype(np.uint8)).save(target / "signature.mask.png")
    (target / "contract.pdf").write_bytes(labelled(second=False))
    ### the invoice's text, the day the shipped template was accepted: `invoice.json` is its input, kept as it is.
    source = (SHIPPED / "invoice.typ").read_bytes()
    data = json.loads((target / "invoice.json").read_text())
    pdf = anyio.run(TypstAdapter(timeout=10.0).compose, source, data, SHIPPED)
    document = pdfium.PdfDocument(pdf)
    (target / "invoice.txt").write_bytes("\f".join(page.get_textpage().get_text_range() for page in document).encode())


if __name__ == "__main__":
    build()
