"""tests/benchmark/e_organon/main: concurrent load on the app `create_app` builds — chains, graph and seal survive a burst;
`make stress` soaks it. Not a unit of one module: every layer answers at once, over the faked services of `tests/conftest`."""

import asyncio

import pytest
from litestar.testing import AsyncTestClient

from e_organon.main import create_app

STREAM: dict[str, str] = {"accept": "text/event-stream"}
READER: dict[str, str] = {"Authorization": "Bearer t-ana"}
ACTORS: int = 8
HEALTH_BURST: int = 50


@pytest.mark.stress
async def test_create_app_stress_concurrent_traffic() -> None:
    """Eight actors call a tool at once, each streamed or batched by turns, while health is hammered: no crosstalk."""

    async def actor(client: AsyncTestClient, i: int) -> None:
        path = {"path": f"/etc/hostname-{i}"}
        batched = await client.post("/doc/convert", json=path, headers=READER)
        assert (batched.status_code, f"hostname-{i}" in batched.json()["detail"]) == (422, True)
        streamed = await client.post("/doc/convert", json=path, headers=READER | STREAM)
        assert (streamed.status_code, f"hostname-{i}" in streamed.text) == (200, True)

    async def health_burst(client: AsyncTestClient) -> None:
        responses = await asyncio.gather(*(client.get("/health") for _ in range(HEALTH_BURST)))
        assert [r.status_code for r in responses] == [200] * HEALTH_BURST

    async with AsyncTestClient(create_app()) as client, asyncio.TaskGroup() as group:
        for i in range(ACTORS):
            group.create_task(actor(client, i))
        group.create_task(health_burst(client))
