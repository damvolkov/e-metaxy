from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from e_metaxy.core import middlewares
from e_metaxy.core.middlewares import AccessLogMiddleware

if TYPE_CHECKING:
    import pytest


async def drop(_message: Any) -> None:
    return None


async def test_middlewares_access_log_passes_non_http_through() -> None:
    seen: list[str] = []

    async def app(scope: Any, _receive: Any, _send: Any) -> None:
        seen.append(scope["type"])

    ### a bare websocket scope: litestar's typed scope union is wider than this test needs to build.
    await AccessLogMiddleware(app)(cast("Any", {"type": "websocket"}), cast("Any", None), drop)
    assert seen == ["websocket"]


async def test_middlewares_access_log_records_the_path_as_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    lines: list[dict[str, Any]] = []
    monkeypatch.setattr(middlewares, "logger", SimpleNamespace(info=lambda event, **kw: lines.append(kw)))

    async def mount(scope: Any, _receive: Any, send: Any) -> None:
        scope["path"] = "/stripped"
        await send({"type": "http.response.start", "status": 200})

    await AccessLogMiddleware(mount)(
        cast("Any", {"type": "http", "method": "GET", "path": "/mcp"}), cast("Any", None), drop
    )
    assert [(line["path"], line["status"]) for line in lines] == [("/mcp", 200)]
