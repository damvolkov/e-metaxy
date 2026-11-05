"""tests/support/ink: a signature already cut out — a transparent PNG with a black stroke — the stamp tools place."""

import io

from PIL import Image, ImageDraw, ImageFont


def ink_png(width: int = 200, height: int = 100) -> bytes:
    """An RGBA PNG of `width` x `height`, clear but for a thick diagonal."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(image).line([(10, height - 10), (width - 10, 10)], fill=(0, 0, 0, 255), width=8)
    sink = io.BytesIO()
    image.save(sink, format="PNG")
    return sink.getvalue()


def quadrants_png(width: int = 120, height: int = 60) -> bytes:
    """An opaque PNG whose quadrants are told apart — red top-left, green top-right, blue bottom-left, black bottom-right —:
    upright only one way."""
    image = Image.new("RGB", (width, height))
    half_w, half_h = width // 2, height // 2
    for box, color in (
        ((0, 0, half_w, half_h), (255, 0, 0)),
        ((half_w, 0, width, half_h), (0, 255, 0)),
        ((0, half_h, half_w, height), (0, 0, 255)),
        ((half_w, half_h, width, height), (0, 0, 0)),
    ):
        image.paste(color, box)
    sink = io.BytesIO()
    image.save(sink, format="PNG")
    return sink.getvalue()


def red_png(width: int = 100, height: int = 50) -> bytes:
    """An opaque red PNG, 2:1."""
    sink = io.BytesIO()
    Image.new("RGB", (width, height), (255, 0, 0)).save(sink, format="PNG")
    return sink.getvalue()


def text_png(text: str = "La factura número 42 está pagada.", size: int = 32) -> bytes:
    """An opaque white PNG with `text` in black at (20, 20), in a font the OCR tests share: a scan, made small."""
    image = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(image).text((20, 20), text, font=ImageFont.truetype("DejaVuSans.ttf", size), fill="black")
    sink = io.BytesIO()
    image.save(sink, format="PNG")
    return sink.getvalue()
