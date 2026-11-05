"""tests/unit/e_organon/mcp/tools/organon: the jobs as an agent meets them — a tool queued over REST, its job read over MCP
(held until it settles when asked to wait) and stopped; an id nobody holds is the tool's error."""

from typing import TYPE_CHECKING

import pytest

from support.mcp import call, refused

if TYPE_CHECKING:
    from pathlib import Path

    from litestar import Litestar
    from litestar.testing import AsyncTestClient

    from support.mcp import Connect


async def queue_convert(client: AsyncTestClient[Litestar], vault: Path, key: dict[str, str]) -> str:
    response = await client.post(
        "/doc/convert", json={"path": str(vault / "plan.md")}, headers={**key, "prefer": "respond-async"}
    )
    return response.json()["job"]


async def test_organon_job_waits_for_the_answer(
    vault: Path, connect: Connect, client: AsyncTestClient[Litestar], ana_key: dict[str, str]
) -> None:
    job = await queue_convert(client, vault, ana_key)
    told = await call(connect, "organon_job", {"job": job, "wait": 5}, ana_key)
    assert (told["id"], told["kind"], told["state"], told["progress"]["done"]["name"]) == (
        job,
        "doc/convert",
        "completed",
        "plan.md",
    )


async def test_organon_cancel_of_a_settled_job_leaves_it_as_it_is(
    vault: Path, connect: Connect, client: AsyncTestClient[Litestar], ana_key: dict[str, str]
) -> None:
    job = await queue_convert(client, vault, ana_key)
    _ = await call(connect, "organon_job", {"job": job, "wait": 5}, ana_key)
    stopped = await call(connect, "organon_cancel", {"job": job}, ana_key)
    assert stopped["state"] == "completed"


@pytest.mark.parametrize("tool", ["organon_job", "organon_cancel"])
async def test_organon_unknown_job_is_the_tool_error(connect: Connect, ana_key: dict[str, str], tool: str) -> None:
    assert await refused(connect, tool, {"job": "nope"}, ana_key) == "unknown job 'nope'"
