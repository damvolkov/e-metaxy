"""tests/unit/e_organon/mcp/tools/organon: the catalog and the jobs as an agent meets them — a tool queued over REST, its job read over MCP
(held until it settles when asked to wait) and stopped; an id nobody holds is the tool's error."""

from typing import TYPE_CHECKING

import pytest

from support.mcp import call, refused

if TYPE_CHECKING:
    from pathlib import Path

    from support.auth import FakeAuth
    from support.jobs import Queued
    from support.mcp import Connect


async def test_organon_job_waits_for_the_answer(queued: Queued, connect: Connect, ana_key: dict[str, str]) -> None:
    job = await queued(ana_key)
    told = await call(connect, "organon_job", {"job": job, "wait": 5}, ana_key)
    assert (told["id"], told["kind"], told["state"], told["progress"]["done"]["name"]) == (
        job,
        "doc/convert",
        "completed",
        "plan.md",
    )


async def test_organon_cancel_of_a_settled_job_leaves_it_as_it_is(
    queued: Queued, connect: Connect, ana_key: dict[str, str]
) -> None:
    job = await queued(ana_key)
    _ = await call(connect, "organon_job", {"job": job, "wait": 5}, ana_key)
    stopped = await call(connect, "organon_cancel", {"job": job}, ana_key)
    assert stopped["state"] == "completed"


@pytest.mark.parametrize("tool", ["organon_job", "organon_cancel"])
async def test_organon_unknown_job_is_the_tool_error(connect: Connect, ana_key: dict[str, str], tool: str) -> None:
    assert await refused(connect, tool, {"job": "nope"}, ana_key) == "unknown job 'nope'"


async def test_organon_find_ranks_the_tools_for_an_agent(connect: Connect, ana_key: dict[str, str]) -> None:
    found = await call(connect, "organon_find", {"query": "split a pdf into pages", "section": "doc"}, ana_key)
    assert found["tools"][0]["name"] == "doc_split"
    assert found["tools"][0]["schema"]["properties"]["ranges"] is not None


@pytest.mark.parametrize("tool", ["organon_job", "organon_cancel"])
async def test_organon_another_accounts_job_is_unknown_the_admin_reads_it(
    queued: Queued, connect: Connect, keys: FakeAuth, ana_key: dict[str, str], root_key: dict[str, str], tool: str
) -> None:
    keys.key("t-bob", "bob")
    job = await queued(ana_key, settled=True)
    refusal = await refused(connect, tool, {"job": job}, {"Authorization": "Bearer t-bob"})
    seen = await call(connect, tool, {"job": job}, root_key)
    assert (refusal, seen["id"]) == (f"unknown job '{job}'", job)


async def test_organon_submit_queues_a_tool_the_job_is_followed_to_completed(
    vault: Path, connect: Connect, ana_key: dict[str, str]
) -> None:
    accepted = await call(
        connect, "organon_submit", {"tool": "doc/convert", "input": {"path": str(vault / "plan.md")}}, ana_key
    )
    told = await call(connect, "organon_job", {"job": accepted["job"], "wait": 5}, ana_key)
    assert (told["kind"], told["state"], told["progress"]["done"]["name"]) == ("doc/convert", "completed", "plan.md")


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"tool": "doc/convert", "input": {"path": 3}}, "Expected `str`"),
        ({"tool": "tekton/start", "input": {}}, "no tool 'tekton/start' runs as a job"),
        ({"tool": "doc/nope", "input": {}}, "no tool 'doc/nope' runs as a job"),
    ],
    ids=["bad-input", "tekton-not-a-job", "unknown"],
)
async def test_organon_submit_refuses_what_cannot_be_a_job(
    connect: Connect, ana_key: dict[str, str], arguments: dict[str, object], reason: str
) -> None:
    assert reason in await refused(connect, "organon_submit", arguments, ana_key)
