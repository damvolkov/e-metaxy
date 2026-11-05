"""tests/unit/e_organon/main: the composition root — a lazy factory, every router registered, the contract stamped."""

import inspect
from importlib.metadata import version
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

import e_organon.main as entrypoint
from e_organon.api.lifespan import engines, mcp, providers, services
from e_organon.infra.settings import settings as st
from e_organon.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator

### the tekton tools, each a `POST /tekton/<tool>`.
TEKTON = ("eng", "start", "status", "tasks", "cancel", "catalog", "find", "read", "update", "peers", "send")


async def test_import_has_no_side_effects() -> None:
    assert callable(entrypoint.create_app)
    assert not hasattr(entrypoint, "app"), "the factory must stay lazy: granian builds it per worker"


async def test_create_app_takes_nothing() -> None:
    assert list(inspect.signature(create_app).parameters) == []


def test_create_app_lifespans_write_the_graph_in_startup_order(client: TestClient) -> None:
    """Infra first, then the providers, the engines over them, the services, the MCP server; sealed last."""
    assert list(client.app.state.system) == ["shared", "providers", "engines", "crypto", "services", "mcp"]


def test_create_app_registers_every_router(client: TestClient) -> None:
    paths = {route.path for route in client.app.routes}
    assert {
        "/health",
        "/ready",
        "/auth/me",
        "/auth/accounts",
        "/auth/accounts/{name:str}/token",
        "/docs",
        "/schema",
        "/doc/convert",
        *(f"/tekton/{tool}" for tool in TEKTON),
    } <= paths


def test_create_app_chains_wire_endpoints_not_the_app(client: TestClient) -> None:
    ### every dependency link is declared by the route that consumes it
    assert client.app.dependencies == {}


def test_create_app_openapi_contract_comes_from_its_owners(client: TestClient) -> None:
    ### the distribution stamps the version; the bearer id is the SecuritySchemeName enum's value.
    config = client.app.openapi_config
    assert config.version == version("e-organon")
    assert "bearerAuth" in config.components.security_schemes


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app as the public image runs it: TEKTON_PROFILES unset, so no coder, no bridge, no `tekton/` tools."""
    off = st.model_copy(update={"TEKTON_PROFILES": None})
    _ = [monkeypatch.setattr(module, "st", off) for module in (entrypoint, providers, engines, services, mcp)]
    with TestClient(create_app()) as test_client:
        yield test_client


def test_create_app_without_profiles_serves_no_bridge(bare: TestClient) -> None:
    system = bare.app.state.system
    paths = {route.path for route in bare.app.routes}
    tools = {entry.path for entry in system.mcp.server.registry}
    assert (system.providers.coder, system.engines.bridge, "tekton" in system.services) == (None, None, False)
    assert not {path for path in paths if path.startswith("/tekton")}
    assert "/doc/convert" in paths
    assert not {path for path in tools if path.startswith("/tekton")}
