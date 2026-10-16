import logging
from typing import TYPE_CHECKING

import httpx2
import pytest
from fakes import lifespan

from e_metaxy.adapters.notifier.openhuman import OpenHumanNotifier
from e_metaxy.config.metaxy import MetaxySettings
from e_metaxy.core.settings.base import Secret
from e_metaxy.main import _ToStructlog, assemble, notifiers
from e_metaxy.mcp.guard import TokenGuard

if TYPE_CHECKING:
    from pathlib import Path

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "host": "127.0.0.1:45190",
}


@pytest.fixture
def settings(resources: Path, tmp_path: Path, fake_claude: str) -> MetaxySettings:
    return MetaxySettings(
        profiles=resources / "profiles" / "book.yaml",
        ledger=tmp_path / "ledger.db",
        claude=fake_claude,
        token=Secret("t"),
    )


@pytest.mark.parametrize(("token", "expected"), [(None, []), (Secret("core"), ["openhuman"])], ids=["off", "on"])
async def test_main_notifiers(token: Secret | None, expected: list[str]) -> None:
    built = notifiers(MetaxySettings(openhuman_token=token))
    assert (list(built), all(isinstance(n, OpenHumanNotifier) for n in built.values())) == (expected, True)


async def test_main_assemble_guarded(settings: MetaxySettings) -> None:
    assert isinstance(assemble(settings), TokenGuard)


async def test_main_quiet_routes_stdlib(settings: MetaxySettings) -> None:
    _ = assemble(settings)
    assert any(isinstance(h, _ToStructlog) for h in logging.root.handlers)
    assert not any(type(h).__module__.startswith("rich") for h in logging.root.handlers)
    logging.getLogger("mcp.test").warning("routed without raising")


async def test_main_assemble_open(settings: MetaxySettings) -> None:
    assert not isinstance(assemble(settings.model_copy(update={"token": None})), TokenGuard)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({**HEADERS, "authorization": "Bearer t"}, 200),
        (HEADERS, 401),
        ({**HEADERS, "authorization": "Bearer wrong"}, 401),
        ({**HEADERS, "authorization": "Bearer t", "host": "evil.example:45190"}, 421),
    ],
    ids=["authorized", "no-token", "wrong-token", "foreign-host"],
)
async def test_main_http_initialize(settings: MetaxySettings, headers: dict, status: int) -> None:
    app = assemble(settings)
    async with (
        lifespan(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url="http://127.0.0.1:45190") as http,
    ):
        response = await http.post("/mcp", json=INIT, headers=headers)
    assert response.status_code == status


async def test_main_http_tool_call(settings: MetaxySettings) -> None:
    app = assemble(settings)
    auth = {**HEADERS, "authorization": "Bearer t"}
    async with (
        lifespan(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url="http://127.0.0.1:45190") as http,
    ):
        init = await http.post("/mcp", json=INIT, headers=auth)
        session = {**auth, "mcp-session-id": init.headers["mcp-session-id"], "mcp-protocol-version": "2025-06-18"}
        await http.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=session)
        call = await http.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "session_list", "arguments": {}},
            },
            headers=session,
        )
    peers = call.json()["result"]["structuredContent"]["result"]
    assert [p["name"] for p in peers] == ["e-engineer-bc", "e-jev-43"]
