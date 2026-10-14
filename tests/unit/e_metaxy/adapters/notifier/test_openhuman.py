from datetime import timedelta
from typing import TYPE_CHECKING

import msgspec
import pytest
from werkzeug import Request, Response

from e_metaxy.adapters.notifier.openhuman import METHOD, OpenHumanNotifier
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import Task, TaskOrder, TaskState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_httpserver import HTTPServer


@pytest.fixture
def ended() -> Task:
    order = TaskOrder(prompt="audit the vault", profile="research", cwd="/tmp", caller="openhuman")
    return Task.open(order, CoderKind.CLAUDE).move(TaskState.DONE, result="clean")


@pytest.fixture
async def notifier(httpserver: HTTPServer) -> AsyncIterator[OpenHumanNotifier]:
    async with OpenHumanNotifier(httpserver.url_for("/rpc"), "core-token", timeout=timedelta(seconds=2)) as opened:
        yield opened


async def test_openhuman_notify(httpserver: HTTPServer, notifier: OpenHumanNotifier, ended: Task) -> None:
    seen: list[dict] = []

    def handle(request: Request) -> Response:
        seen.append({"auth": request.headers.get("Authorization"), **msgspec.json.decode(request.get_data())})
        return Response('{"jsonrpc":"2.0","id":1,"result":{}}', content_type="application/json")

    httpserver.expect_request("/rpc", method="POST").respond_with_handler(handle)
    await notifier.notify(ended)
    (call,) = seen
    assert (call["auth"], call["method"], call["params"]["caller_id"], call["params"]["payload"]["result"]) == (
        "Bearer core-token",
        METHOD,
        f"e-metaxy:{ended.id}",
        "clean",
    )


async def test_openhuman_notify_swallows_failure(
    httpserver: HTTPServer, notifier: OpenHumanNotifier, ended: Task
) -> None:
    httpserver.expect_request("/rpc", method="POST").respond_with_data("down", status=503)
    assert await notifier.notify(ended) is None


async def test_openhuman_unconnected(ended: Task) -> None:
    with pytest.raises(RuntimeError, match="not connected"):
        OpenHumanNotifier("http://127.0.0.1:1/rpc", "t")._common_connected()


async def test_openhuman_close_idempotent() -> None:
    notifier = OpenHumanNotifier("http://127.0.0.1:1/rpc", "t")
    await notifier.close()
    assert notifier._client is None
