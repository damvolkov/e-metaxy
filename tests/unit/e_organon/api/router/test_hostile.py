"""tests/unit/e_organon/api/router/hostile: every doc/ and image/ tool against the hostile corpus (`tests/resources/hostile`) on the
whole stack — a clean answer each time, and quick: a `Failed` as 422 `kind: reason`, or a success where success is safe. Never
a 500, never a hang. Per tool and file the verdict is told below; what is not in a list is "either, but clean".

- JavaScript, a launch action, a URI in a PDF are inert to every engine here (qpdf, pdfium, liteparse, anytomd read the
  bytes; none runs an action): the tools that read the PDF succeed, and `doc/fill` finds no field to fill.
- A PNG or JPEG whose header claims 4.3 gigapixels is refused from the header (ORGANON_MAX_PIXELS), unread; `doc/convert`
  does not decode an image's pixels and answers.
- A PDF of 20 000 pages is refused by every tool that opens it page by page or edits it (ORGANON_MAX_PAGES); `doc/convert` reads
  a text, not pages, and answers.
- A symlink out of the roots is `OutsideRootsError` wherever a path is taken, the image of a stamp and the photo of a signature too."""

import time
from typing import TYPE_CHECKING, Any, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from litestar.testing import TestClient

BOX: Final[dict[str, Any]] = {"type": "box", "page": 0, "x": 10, "y": 10, "width": 50}
QUICK: Final[float] = 10.0

### a tool's request for a hostile `file`, the good PDF and image beside it where the tool takes two.
TOOLS: Final[dict[str, Callable[[str, Path], tuple[str, dict[str, Any]]]]] = {
    "doc/convert": lambda file, vault: ("/doc/convert", {"path": file}),
    "doc/inspect": lambda file, vault: ("/doc/inspect", {"path": file}),
    "doc/merge": lambda file, vault: ("/doc/merge", {"paths": [file, str(vault / "labelled.pdf")]}),
    "doc/split": lambda file, vault: ("/doc/split", {"path": file, "ranges": [[0, 0]]}),
    "doc/fill": lambda file, vault: ("/doc/fill", {"path": file, "values": {"x": "y"}}),
    "doc/render": lambda file, vault: ("/doc/render", {"path": file}),
    "doc/stamp": lambda file, vault: ("/doc/stamp", {"path": file, "text": "x", "at": BOX}),
    "doc/stamp(image)": lambda file, vault: (
        "/doc/stamp",
        {"path": str(vault / "labelled.pdf"), "image": file, "at": BOX},
    ),
    "doc/signature(photo)": lambda file, vault: (
        "/doc/signature",
        {"path": str(vault / "labelled.pdf"), "photo": file, "at": BOX},
    ),
    "image/cutout": lambda file, vault: ("/image/cutout", {"path": file}),
}
FILES: Final[tuple[str, ...]] = (
    "pixel-bomb.png",
    "pixel-bomb.jpg",
    "big-header.png",
    "bad-crc.png",
    "javascript.pdf",
    "many-pages.pdf",
    "truncated.pdf",
    "garbage.pdf",
    "empty.pdf",
    "empty.png",
    "not-an-image.png",
    "escape",
)
PDF_TOOLS: Final[tuple[str, ...]] = ("doc/inspect", "doc/merge", "doc/split", "doc/fill", "doc/render", "doc/stamp")
IMAGE_TOOLS: Final[tuple[str, ...]] = ("doc/stamp(image)", "doc/signature(photo)", "image/cutout")
NOT_PDF: Final[tuple[str, ...]] = (
    "pixel-bomb.png",
    "pixel-bomb.jpg",
    "big-header.png",
    "bad-crc.png",
    "garbage.pdf",
    "empty.pdf",
    "empty.png",
    "not-an-image.png",
)
NOT_IMAGE: Final[tuple[str, ...]] = (
    "javascript.pdf",
    "many-pages.pdf",
    "truncated.pdf",
    "garbage.pdf",
    "empty.pdf",
    "empty.png",
    "not-an-image.png",
    "bad-crc.png",
)

### what each (tool, file) must answer; whatever is not here may answer 200 or 422, but cleanly.
REFUSED: Final[frozenset[tuple[str, str]]] = frozenset(
    {(tool, file) for tool in PDF_TOOLS for file in (*NOT_PDF, "many-pages.pdf", "escape")}
    | {
        (tool, file)
        for tool in IMAGE_TOOLS
        for file in (*NOT_IMAGE, "pixel-bomb.png", "pixel-bomb.jpg", "big-header.png", "escape")
        ### Pillow, which a stamp's image goes through, does not check an IDAT chunk's CRC and reads the file: a safe success.
        if (tool, file) != ("doc/stamp(image)", "bad-crc.png")
    }
    | {
        ("doc/convert", "escape"),
        ("doc/convert", "garbage.pdf"),
        ("doc/convert", "truncated.pdf"),
        ("doc/convert", "empty.pdf"),
    }
)
SAFE: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        (tool, "javascript.pdf")
        for tool in ("doc/convert", "doc/inspect", "doc/merge", "doc/split", "doc/render", "doc/stamp")
    }
    | {("doc/convert", "many-pages.pdf")}
)


@pytest.mark.parametrize("file", FILES)
@pytest.mark.parametrize("tool", TOOLS)
def test_hostile_every_tool_answers_cleanly_and_quickly(
    hostile: Path, client: TestClient, ana_key: dict[str, str], tool: str, file: str
) -> None:
    path, body = TOOLS[tool](str(hostile / file), hostile.parent)
    started = time.perf_counter()
    response = client.post(path, json=body, headers=ana_key)
    took = time.perf_counter() - started
    expected = 422 if (tool, file) in REFUSED else 200 if (tool, file) in SAFE else response.status_code
    assert (response.status_code in {200, 422}, response.status_code == expected, took < QUICK) == (True, True, True), (
        response.status_code,
        response.text[:200],
        took,
    )


@pytest.mark.parametrize(
    ("file", "kind"),
    [
        ("pixel-bomb.png", "ParseError"),
        ("pixel-bomb.jpg", "ParseError"),
        ("big-header.png", "ImageTooLargeError"),
    ],
    ids=["png-over-pillows-limit", "jpg-over-pillows-limit", "over-the-budget"],
)
def test_hostile_a_pixel_bomb_is_refused_for_its_pixels(
    hostile: Path, client: TestClient, ana_key: dict[str, str], file: str, kind: str
) -> None:
    """Over Pillow's own bomb limit (179 MP) the header read itself refuses; between the budget (40 MP) and that, the service."""
    response = client.post("/image/cutout", json={"path": str(hostile / file)}, headers=ana_key)
    detail = response.json()["detail"]
    assert (response.status_code, detail.startswith(kind), "pixels" in detail) == (422, True, True)


def test_hostile_too_many_pages_is_refused_for_its_pages(
    hostile: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    response = client.post("/doc/inspect", json={"path": str(hostile / "many-pages.pdf")}, headers=ana_key)
    assert (response.status_code, "pages" in response.json()["detail"]) == (422, True)


def test_hostile_a_symlink_out_of_the_roots_is_outside_them(
    hostile: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    response = client.post("/doc/inspect", json={"path": str(hostile / "escape")}, headers=ana_key)
    assert response.json()["detail"].startswith("OutsideRootsError")
