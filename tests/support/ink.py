"""tests/support/ink: a signature already cut out — a transparent PNG with a black stroke — the stamp tools place."""

import io

from PIL import Image, ImageDraw


def ink_png(width: int = 200, height: int = 100) -> bytes:
    """An RGBA PNG of `width` x `height`, clear but for a thick diagonal."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(image).line([(10, height - 10), (width - 10, 10)], fill=(0, 0, 0, 255), width=8)
    sink = io.BytesIO()
    image.save(sink, format="PNG")
    return sink.getvalue()
