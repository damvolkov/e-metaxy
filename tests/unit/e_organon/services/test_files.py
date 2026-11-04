"""tests/unit/e_organon/services/files: a path is a file under an allowed root, after links and `..` are resolved."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.error import OutsideRootsError
from e_organon.services.files import AllowedFiles

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    inside = tmp_path / "vault"
    inside.mkdir()
    (inside / "note.md").write_text("# note")
    return inside


async def test_files_resolve_inside(root: Path) -> None:
    assert await AllowedFiles((root,)).resolve(str(root / "note.md")) == (root / "note.md").resolve()


@pytest.mark.parametrize("name", ["../escape.md", "missing.md", "."], ids=["dotdot", "missing", "folder"])
async def test_files_refuse(root: Path, name: str) -> None:
    (root.parent / "escape.md").write_text("x")
    with pytest.raises(OutsideRootsError):
        await AllowedFiles((root,)).resolve(str(root / name))


async def test_files_refuse_a_link_out(root: Path) -> None:
    (root.parent / "secret.md").write_text("x")
    (root / "link.md").symlink_to(root.parent / "secret.md")
    with pytest.raises(OutsideRootsError):
        await AllowedFiles((root,)).resolve(str(root / "link.md"))


async def test_files_default_roots_are_the_settings() -> None:
    assert AllowedFiles()._roots
