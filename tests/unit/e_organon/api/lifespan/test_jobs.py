"""tests/unit/e_organon/api/lifespan/jobs: the dispatch entered once the services exist — on the durable queue when it
answers, on memory when it does not."""

from typing import TYPE_CHECKING

from litestar.testing import TestClient

from e_organon.main import create_app

if TYPE_CHECKING:
    from support.queue import FakeQueue


def test_jobs_dispatch_runs_in_memory_when_the_queue_is_down(client: TestClient) -> None:
    assert client.app.state.system.engines.dispatch.engine == "memory"


def test_jobs_dispatch_prefers_the_durable_queue_when_it_answers(queue: FakeQueue) -> None:
    queue.up = True
    with TestClient(create_app()) as client:
        assert client.app.state.system.engines.dispatch.engine == "fake-queue"
