"""tests/unit/e_organon/services/doc/render: the asked pages as PNG, every page when none is asked."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.doc import RenderIn
from e_organon.services.doc.render import RenderDocService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(("pages", "expected"), [([], 3), ([1], 1)], ids=["all", "one"])
async def test_render_draws_pages(render, files, artifacts, vault: Path, pages: list[int], expected: int) -> None:
    out = await RenderDocService(render, files, artifacts).run(
        RenderIn(path=str(vault / "three.pdf"), pages=pages, dpi=36)
    )
    assert [file.path.endswith(".png") for file in out.files] == [True] * expected
