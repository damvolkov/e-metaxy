"""tests/unit/e_organon/services/organon/find: the tools ranked against a need, deterministically — a word in a tool's name
weighs 4, in its title 2, in its description 1; ties by name; at most five; a section narrows, an empty query lists it."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.flow import Done, Step
from e_organon.models.organon import FindIn, FindOut

if TYPE_CHECKING:
    from e_organon.services.organon.find import FindOrganonService
    from support.catalog import Ranked


@pytest.mark.parametrize(
    ("query", "section", "first"),
    [
        ("merge pdfs", "", ["doc_merge"]),
        ("how ready is the service", "", ["api_status"]),
        ("cancel", "", ["organon_cancel", "tekton_cancel"]),
        ("cancel", "tekton", ["tekton_cancel"]),
        ("Cancel", "TEKTON", ["tekton_cancel"]),
    ],
    ids=["merge", "readiness", "ties-by-name", "section", "case"],
)
async def test_find_ranks_the_tools_that_answer(
    find: FindOrganonService, ranked: Ranked, query: str, section: str, first: list[str]
) -> None:
    assert (await ranked(find, query, section))[: len(first)] == first


async def test_find_weighs_the_name_over_the_title_over_the_description(
    weighed: FindOrganonService, ranked: Ranked
) -> None:
    assert await ranked(weighed, "zebra") == ["wave_zebra", "wave_beta", "wave_gamma"]


async def test_find_answers_name_description_and_input_schema(weighed: FindOrganonService) -> None:
    found = (await weighed.run(FindIn(query="alpha"))).tools[0]
    assert (found.name, found.description, found.schema) == (
        "wave_zebra",
        "Alpha.",
        {"type": "object", "properties": {"id": {"type": "string"}}},
    )


async def test_find_an_empty_query_lists_the_section_by_name(find: FindOrganonService, ranked: Ranked) -> None:
    assert await ranked(find, "", "doc") == ["doc_convert", "doc_fill", "doc_inspect", "doc_merge", "doc_render"]


@pytest.mark.parametrize(("query", "section"), [("zzzz", ""), ("merge", "nope"), ("merge", "tekton")])
async def test_find_nothing_that_answers_is_nothing(
    find: FindOrganonService, ranked: Ranked, query: str, section: str
) -> None:
    assert await ranked(find, query, section) == []


async def test_find_answers_at_most_five_the_same_every_time(find: FindOrganonService, ranked: Ranked) -> None:
    first, second = await ranked(find, "pdf page file path"), await ranked(find, "pdf page file path")
    assert (len(first) <= 5, first == second) == (True, True)


async def test_find_is_one_step_then_the_answer(find: FindOrganonService) -> None:
    events = [event async for event in find.events(FindIn(query="merge"))]
    assert events[0] == Step(name="rank", index=0, total=1)
    assert isinstance(events[-1], Done)
    assert isinstance(events[-1].result, FindOut)
