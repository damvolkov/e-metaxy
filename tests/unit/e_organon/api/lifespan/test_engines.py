"""tests/unit/e_organon/api/lifespan/engines: every provider surveyed at startup — one event each, never a failed start; the
admin's account made there, never a key."""

from dataclasses import fields
from typing import TYPE_CHECKING, Final, cast

from litestar.testing import TestClient

from e_organon.api.lifespan import engines
from e_organon.api.lifespan.engines import QUEUES, EnginesState
from e_organon.api.lifespan.providers import OPTIONAL, ProvidersState
from e_organon.engines.auth import AuthEngine
from e_organon.engines.bridge import BridgeEngine
from e_organon.engines.dispatch import DispatchEngine
from e_organon.infra.auth.models import Role
from e_organon.infra.config.engines import QueueEngine
from e_organon.infra.settings import Settings
from e_organon.infra.settings import settings as st
from e_organon.main import create_app
from e_organon.ops.crypto import Crypto
from e_organon.providers.drivers.queue.pgqueuer import PgqueuerDriver
from e_organon.providers.drivers.store.sqlite import SqliteDriver

if TYPE_CHECKING:
    import pytest

    from e_organon.ports.database import DatabaseListenPort
    from support.auth import FakeAuth
    from support.coder import ScriptedCoder

### the roles are the section's fields: a provider the export drops leaves this list with it.
### an optional role is empty here (no DOCLING_URL in tests): the roles are the section's other fields.
ROLES: Final[tuple[str, ...]] = tuple(each.name for each in fields(ProvidersState) if each.name not in OPTIONAL)


async def test_engines_section_is_typed(client: TestClient) -> None:
    section = client.app.state.system.engines
    assert isinstance(section, EnginesState)
    assert isinstance(section.auth, AuthEngine)
    assert isinstance(section.bridge, BridgeEngine)
    assert isinstance(section.dispatch, DispatchEngine)


async def test_engines_health_surveys_every_provider(client: TestClient) -> None:
    """In field order, `store` and `auth` the required ones; the open sqlite file and the open client always answer."""
    verdicts = {verdict.name: verdict for verdict in await client.app.state.system.engines.health.survey()}
    assert tuple(verdicts) == ROLES
    assert [verdicts[name].required for name in ROLES] == [name in {"store", "auth"} for name in ROLES]
    assert verdicts["store"].ok


async def test_engines_startup_logs_each_verdict(
    monkeypatch: pytest.MonkeyPatch, logs: list[tuple[str, str, dict[str, object]]]
) -> None:
    """One event per provider as the app starts: info when it answers, a warning when it does not — the app starts."""

    async def down(_self: SqliteDriver) -> bool:
        return False

    monkeypatch.setattr(SqliteDriver, "health", down)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    verdicts = {
        fields["provider"]: {"log_level": level, **fields}
        for level, event, fields in logs
        if event == "provider health"
    }
    assert tuple(verdicts) == ROLES
    assert (verdicts["store"]["log_level"], verdicts["store"]["ok"], verdicts["store"]["reason"]) == (
        "warning",
        False,
        "unhealthy",
    )
    assert not any(verdicts[name]["required"] for name in ROLES if name not in {"store", "auth"})


def test_engines_startup_makes_the_admin_account_and_no_key(keys: FakeAuth) -> None:
    held = len(keys.grants)
    with TestClient(create_app()):
        secret = st.AUTH_SECRET
        assert secret is not None
        made = keys.owners[Crypto.identify(secret.get_secret_value(), "admin")]
    assert (made.name, made.role, len(keys.grants)) == ("admin", Role.ADMIN, held)


def test_engines_startup_without_a_secret_makes_no_account(monkeypatch: pytest.MonkeyPatch, keys: FakeAuth) -> None:
    monkeypatch.setattr(engines, "st", Settings(AUTH_SECRET=None))
    before = dict(keys.owners)
    with TestClient(create_app()):
        assert keys.owners == before


def test_engines_bridge_cancels_what_runs_when_the_app_stops(ana_key: dict[str, str], coder: ScriptedCoder) -> None:
    """A run parked on the coder is cancelled by the stop, and the ledger — the app's store — says so to the next one."""
    coder.hold = True
    body = {"prompt": "ping", "project": "/tmp", "profile": "research"}
    with TestClient(create_app()) as first:
        task = first.post("/tekton/start", json=body, headers=ana_key).json()
        assert (
            first.post("/tekton/status", json={"task": task["id"], "wait": 0.5}, headers=ana_key).json()["state"]
            == "running"
        )
    with TestClient(create_app()) as second:
        after = second.post("/tekton/status", json={"task": task["id"]}, headers=ana_key).json()
    assert after["state"] == "cancelled"


def test_engines_queue_row_is_pgqueuer() -> None:
    """The default engine is PgQueuer, built from the QUEUE_* settings over the queue's database."""
    assert isinstance(QUEUES[QueueEngine.PGQUEUER](cast("DatabaseListenPort", object())), PgqueuerDriver)
