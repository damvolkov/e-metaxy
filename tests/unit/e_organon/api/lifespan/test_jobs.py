"""tests/unit/e_organon/api/lifespan/jobs: the dispatch entered once the services exist — every tool but the bridge's a
kind on its section's queue, on the durable queue when it answers, on memory when it does not."""

from typing import TYPE_CHECKING

from litestar.testing import TestClient

from e_organon.main import create_app
from e_organon.services.jobs import JobsService

if TYPE_CHECKING:
    from support.queue import FakeQueue

DOC_KINDS = {
    f"doc/{word}": "doc"
    for word in ("convert", "inspect", "merge", "split", "fill", "render", "stamp", "signature", "compose")
}
KINDS = DOC_KINDS | {"image/cutout": "image"}


def test_jobs_dispatch_runs_in_memory_when_the_queue_is_down(client: TestClient) -> None:
    assert client.app.state.system.engines.dispatch.engine == "memory"


def test_jobs_every_tool_is_a_kind_but_the_bridge_and_the_catalog(client: TestClient) -> None:
    system = client.app.state.system
    assert isinstance(system.services.jobs, JobsService)
    assert (system.services.jobs.kinds, system.engines.dispatch.kinds) == (KINDS, frozenset(KINDS))


def test_jobs_dispatch_prefers_the_durable_queue_when_it_answers(queue: FakeQueue) -> None:
    """The kinds are bound on the durable queue, its slots the settings' — `ORGANON_SLOTS_DOC` for the doc queue."""
    queue.up = True
    with TestClient(create_app()) as client:
        assert client.app.state.system.engines.dispatch.engine == "fake-queue"
        assert (set(queue.kinds), queue.slots) == (set(KINDS), {"doc": 2, "image": 2})
