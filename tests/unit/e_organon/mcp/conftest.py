"""tests/unit/e_organon/mcp: the MCP door as a client meets it — the real app over the fake accounts and the in-memory store, its
endpoint reached by the SDK's own client (`support/mcp`): none is nobody, `ana_key` and `root_key` carry the keys of an
account and the admin.

`client` here is the async one the SDK client needs (the lifespans run for the test's length);
`connect` opens the SDK client on `/mcp`."""

from typing import TYPE_CHECKING

import pytest
from litestar.testing import AsyncTestClient

from e_organon.main import create_app
from support.mcp import BASE, connect

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from litestar import Litestar

__all__ = ["app", "client", "connect"]


@pytest.fixture
def app() -> Litestar:
    return create_app()


@pytest.fixture
async def client(app: Litestar) -> AsyncIterator[AsyncTestClient[Litestar]]:
    async with AsyncTestClient(app, base_url=BASE) as running:
        yield running
