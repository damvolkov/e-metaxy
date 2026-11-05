"""tests/unit/e_organon/mcp/tools: what the tool tests start from — `queued`, a document converted in the background over REST
on the running app, its job's id.

The in-process MCP client runs a tool's route on the test's own loop, while the app's lifespans — the dispatch, its jobs
and their `anyio.Event`s — live on the loop of the REST test client. An event set on one loop does not wake a waiter on
the other until something else stirs it, so a tool must never wait on a job that is still running: `organon_cancel` does
(it awaits the job's end), and it hung one run in a hundred under load. Such a test asks for a `settled` job: the REST
client — on the app's loop — waits for the end of the job's events first, a condition, not a sleep."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from litestar import Litestar
    from litestar.testing import AsyncTestClient

    from support.jobs import Queued


@pytest.fixture
def queued(vault: Path, client: AsyncTestClient[Litestar]) -> Queued:
    """The id of a `doc/convert` of the vault's plan queued with `Prefer: respond-async` under the given key; `settled`,
    once its events have ended."""

    async def queue(key: dict[str, str], *, settled: bool = False) -> str:
        response = await client.post(
            "/doc/convert", json={"path": str(vault / "plan.md")}, headers={**key, "prefer": "respond-async"}
        )
        job = response.json()["job"]
        _ = settled and await client.get(f"/jobs/{job}/events", headers=key)
        return job

    return queue
