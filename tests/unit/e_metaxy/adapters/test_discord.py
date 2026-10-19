from datetime import timedelta
from typing import TYPE_CHECKING

import msgspec
import pytest
from werkzeug import Request, Response

from e_metaxy.adapters.discord import LIMIT, DiscordAdapter
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import Task, TaskOrder, TaskState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_httpserver import HTTPServer


def ended(state: TaskState, **outcome: str) -> Task:
    order = TaskOrder(prompt="fix the vad", profile="code", cwd="/w/e-voice", caller="discord")
    task = Task.open(order, CoderKind.CLAUDE)
    return msgspec.structs.replace(task, session="7b4fb561-4dde").move(state, **outcome)


@pytest.fixture
async def notifier(httpserver: HTTPServer) -> AsyncIterator[DiscordAdapter]:
    async with DiscordAdapter(httpserver.url_for("/hook"), timeout=timedelta(seconds=2)) as opened:
        yield opened


async def test_discord_notify_posts_the_outcome(httpserver: HTTPServer, notifier: DiscordAdapter) -> None:
    seen: list[dict] = []

    def handle(request: Request) -> Response:
        seen.append(msgspec.json.decode(request.get_data()))
        return Response(status=204)

    httpserver.expect_request("/hook", method="POST").respond_with_handler(handle)
    await notifier.notify(ended(TaskState.DONE, result="threshold lowered, tests green"))
    ((call,),) = [seen]
    assert call["content"].startswith("✅ Claude terminó · e-voice · sesión `7b4fb561`")
    assert "threshold lowered" in call["content"]
    assert "`eng @7b4fb561: …`" in call["content"]
    assert call["allowed_mentions"] == {"parse": []}


@pytest.mark.parametrize(
    ("state", "outcome", "mark"),
    [(TaskState.FAILED, {"error": "boom"}, "❌"), (TaskState.CANCELLED, {}, "⏹")],
)
def test_discord_content_marks_the_end(state: TaskState, outcome: dict, mark: str) -> None:
    assert DiscordAdapter._notify_content(ended(state, **outcome)).startswith(mark)


def test_discord_content_fits_discord() -> None:
    assert len(DiscordAdapter._notify_content(ended(TaskState.DONE, result="x" * 5000))) <= LIMIT


async def test_discord_notify_failure_is_only_logged(httpserver: HTTPServer, notifier: DiscordAdapter) -> None:
    httpserver.expect_request("/hook", method="POST").respond_with_data("nope", status=500)
    await notifier.notify(ended(TaskState.DONE, result="ok"))


async def test_discord_unopened_is_logged_and_closes_clean() -> None:
    adapter = DiscordAdapter("http://x")
    with pytest.raises(RuntimeError, match="not connected"):
        adapter._common_connected()
    await adapter.notify(ended(TaskState.DONE, result="ok"))
    await adapter.close()
