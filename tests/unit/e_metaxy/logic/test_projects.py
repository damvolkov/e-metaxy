from typing import TYPE_CHECKING

import pytest

from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.error import AmbiguousProjectError, UnknownProjectError

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def index(tmp_path: Path) -> ProjectIndex:
    for project in ("damien/e-voice", "damien/e-engineer", "thirdparty/openhuman", "solo", "a/twin", "b/twin"):
        (tmp_path / project).mkdir(parents=True)
    (tmp_path / "damien" / "notes.txt").write_text("not a project")
    return ProjectIndex(tmp_path)


def test_projects_short_name_two_levels(index: ProjectIndex) -> None:
    assert index.resolve("e-voice") == f"{index.root}/damien/e-voice"


def test_projects_short_name_top_level(index: ProjectIndex) -> None:
    assert index.resolve("solo") == f"{index.root}/solo"


def test_projects_path_as_given(index: ProjectIndex, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/someone")
    assert index.resolve("~/x/y") == "/home/someone/x/y"
    assert index.resolve("/abs/path") == "/abs/path"


def test_projects_empty_is_the_root(index: ProjectIndex) -> None:
    assert index.resolve("  ") == index.root


def test_projects_unknown_suggests_close_names(index: ProjectIndex) -> None:
    with pytest.raises(UnknownProjectError, match="close: e-engineer"):
        index.resolve("engineer")


def test_projects_ambiguous_lists_paths(index: ProjectIndex) -> None:
    with pytest.raises(AmbiguousProjectError, match="names several projects"):
        index.resolve("twin")


def test_projects_file_is_not_a_project(index: ProjectIndex) -> None:
    with pytest.raises(UnknownProjectError):
        index.resolve("notes.txt")
