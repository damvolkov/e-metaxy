"""tests/unit/e_organon/ops: a workspace of projects on a temporary root — two levels, a file, a name twice."""

from typing import TYPE_CHECKING

import pytest

from e_organon.ops.projects import NamedProjects

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def projects(tmp_path: Path) -> NamedProjects:
    _ = [
        (tmp_path / project).mkdir(parents=True)
        for project in ("damien/e-voice", "damien/e-engineer", "thirdparty/openhuman", "solo", "a/twin", "b/twin")
    ]
    (tmp_path / "damien" / "notes.txt").write_text("not a project")
    return NamedProjects(tmp_path)
