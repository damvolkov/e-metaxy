"""tests/unit/e_organon/ops/projects: a project by short name (one and two levels deep) or by path, refused with what
it could have meant."""

import pytest

from e_organon.ops.projects import AmbiguousProjectError, NamedProjects, UnknownProjectError


async def test_projects_short_name_two_levels(projects: NamedProjects) -> None:
    assert projects.resolve("e-voice") == f"{projects.root}/damien/e-voice"


async def test_projects_short_name_top_level(projects: NamedProjects) -> None:
    assert projects.resolve("solo") == f"{projects.root}/solo"


async def test_projects_path_as_given(projects: NamedProjects, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/someone")
    assert (projects.resolve("~/x/y"), projects.resolve("/abs/path")) == ("/home/someone/x/y", "/abs/path")


async def test_projects_empty_is_the_root(projects: NamedProjects) -> None:
    assert projects.resolve("  ") == projects.root


async def test_projects_unknown_suggests_close_names(projects: NamedProjects) -> None:
    with pytest.raises(UnknownProjectError, match="close: e-engineer"):
        projects.resolve("engineer")


async def test_projects_unknown_without_a_close_name_says_only_that(projects: NamedProjects) -> None:
    with pytest.raises(UnknownProjectError, match=r"no project named 'zzz' under the workspace$"):
        projects.resolve("zzz")


async def test_projects_ambiguous_lists_paths(projects: NamedProjects) -> None:
    with pytest.raises(AmbiguousProjectError, match="names several projects"):
        projects.resolve("twin")


async def test_projects_file_is_not_a_project(projects: NamedProjects) -> None:
    with pytest.raises(UnknownProjectError):
        projects.resolve("notes.txt")
