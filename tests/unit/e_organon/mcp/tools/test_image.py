"""tests/unit/e_organon/mcp/tools/image: image/cutout as an agent meets it — the PNG's path back, a refusal as the tool's
error."""

from typing import TYPE_CHECKING

from support.mcp import call, refused

if TYPE_CHECKING:
    from pathlib import Path

    from support.mcp import Connect


async def test_image_cutout_answers_the_pngs_path(vault: Path, connect: Connect, ana_key: dict[str, str]) -> None:
    out = await call(connect, "image_cutout", {"path": str(vault / "firma.jpg"), "color": False}, ana_key)
    assert (out["path"].endswith(".png"), out["size"] > 0) == (True, True)


async def test_image_cutout_refuses_outside_the_roots(connect: Connect, ana_key: dict[str, str]) -> None:
    assert "OutsideRootsError" in await refused(connect, "image_cutout", {"path": "/etc/hostname"}, ana_key)


async def test_doc_stamp_and_signature_as_tools(vault: Path, connect: Connect, ana_key: dict[str, str]) -> None:
    at = {"type": "field", "field": "nope"}
    assert "FieldNotFoundError" in await refused(
        connect, "doc_stamp", {"path": str(vault / "labelled.pdf"), "text": "x", "at": at}, ana_key
    )
    signed = await call(
        connect,
        "doc_signature",
        {
            "path": str(vault / "labelled.pdf"),
            "photo": str(vault / "firma.jpg"),
            "at": {"type": "anchor", "anchor": "firma:"},
        },
        ana_key,
    )
    assert signed["path"].endswith(".pdf")


async def test_image_convert_answers_the_files_path(vault: Path, connect: Connect, ana_key: dict[str, str]) -> None:
    out = await call(
        connect, "image_convert", {"path": str(vault / "firma.jpg"), "format": "png", "rotate": 90}, ana_key
    )
    assert (out["path"].endswith(".png"), out["size"] > 0) == (True, True)


async def test_image_convert_refuses_outside_the_roots(connect: Connect, ana_key: dict[str, str]) -> None:
    assert "OutsideRootsError" in await refused(connect, "image_convert", {"path": "/etc/hostname"}, ana_key)


async def test_image_barcode_writes_a_code_and_reads_it_back(
    vault: Path, connect: Connect, ana_key: dict[str, str]
) -> None:
    written = await call(connect, "image_barcode", {"text": "https://example.org", "scale": 6}, ana_key)
    read = await call(connect, "image_barcode", {"path": written["file"]["path"]}, ana_key)
    assert [code["text"] for code in read["codes"]] == ["https://example.org"]


async def test_image_barcode_refuses_a_call_with_neither(connect: Connect, ana_key: dict[str, str]) -> None:
    assert "one of the two" in await refused(connect, "image_barcode", {}, ana_key)
