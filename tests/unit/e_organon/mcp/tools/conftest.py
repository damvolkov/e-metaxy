"""tests/unit/e_organon/mcp/tools: what the tool tests start from — `queued`, a document converted in the background over REST
on the running app, its job's id."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from litestar import Litestar
    from litestar.testing import AsyncTestClient

    from support.jobs import Queued


@pytest.fixture
def queued(vault: Path, client: AsyncTestClient[Litestar]) -> Queued:
    """The id of a `doc/convert` of the vault's plan queued with `Prefer: respond-async` under the given key."""

    async def queue(key: dict[str, str]) -> str:
        response = await client.post(
            "/doc/convert", json={"path": str(vault / "plan.md")}, headers={**key, "prefer": "respond-async"}
        )
        return response.json()["job"]

    return queue
