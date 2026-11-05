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
