"""tests/unit/e_organon/api/lifespan/services: crypto written to the graph, no resource to close."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from e_organon.api.lifespan import services
from e_organon.api.state import AppState
from e_organon.infra.state import State
from e_organon.ops.crypto import Crypto
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.testing import TestClient

TEKTON = ("eng", "start", "status", "tasks", "cancel", "catalog", "find", "read", "update", "peers", "send")


async def test_services_write_crypto_to_the_graph() -> None:
    """Crypto is the one engine the services concern writes; it owns no resource to close."""
    app = SimpleNamespace(state=AppState({"system": State()}))
    async with services.lifespan(cast("Litestar", app)):
        assert isinstance(app.state.system.crypto, Crypto)


async def test_services_crypto_hashes_what_it_verifies() -> None:
    app = SimpleNamespace(state=AppState({"system": State()}))
    async with services.lifespan(cast("Litestar", app)):
        crypto = app.state.system.crypto
        hashed = await crypto.hash_password("correct-horse-1")
        assert await crypto.verify_password("correct-horse-1", hashed)


async def test_services_tekton_tools_hang_at_their_names(client: TestClient) -> None:
    """Each tool under `services.tekton.<tool>`; `update`, a method of the state, is read by key."""
    tekton = client.app.state.system.services.tekton
    assert (sorted(tekton), all(isinstance(tekton[tool], ToolFlow) for tool in TEKTON)) == (sorted(TEKTON), True)
