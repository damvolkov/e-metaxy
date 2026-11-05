"""tests/support/app: the services behind the live app, faked — redis from fakeredis, Postgres from the scripted pool of
`support.psqlpy`, the accounts and keys from the dicts of `support.auth`, the coder a script of `support.coder` — no
Claude Code is ever spawned. Every tier's conftest takes these fixtures."""

import fakeredis
import fakeredis.aioredis
import pytest

from e_organon.api.lifespan import providers as providers_module
from e_organon.infra.auth.models import Role
from e_organon.providers.drivers.database import psqlpy as psqlpy_module
from e_organon.providers.drivers.store import redis as redis_module
from support.auth import FakeAuth
from support.coder import ScriptedCoder
from support.psqlpy import FakePsqlpyServer


@pytest.fixture(autouse=True)
def redis_server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeServer:
    """The redis every driver of the test talks to: an in-memory server, `connected = False` takes it down."""
    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        redis_module.redis, "from_url", lambda _url, **_kwargs: fakeredis.aioredis.FakeRedis(server=server)
    )
    return server


@pytest.fixture(autouse=True)
def psqlpy(monkeypatch: pytest.MonkeyPatch) -> FakePsqlpyServer:
    """The Postgres the db lifespan provisions on: scripted rows and recorded SQL, no database."""
    server = FakePsqlpyServer()
    monkeypatch.setattr(psqlpy_module, "ConnectionPool", server.pool)
    return server


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeAuth:
    """The accounts and keys of the test: the lifespan opens this store where it would open Postgres."""
    store = FakeAuth()
    store.key("t-ana", "ana")
    store.key("t-root", "root", Role.ADMIN)
    monkeypatch.setattr(providers_module, "PostgresAuthDriver", lambda _database: store)
    return store


@pytest.fixture(autouse=True)
def coder(monkeypatch: pytest.MonkeyPatch) -> ScriptedCoder:
    """The coder the lifespan opens where it would open Claude Code: one script, `DONE_SCRIPT`, for every run."""
    scripted = ScriptedCoder()
    monkeypatch.setattr(providers_module, "ClaudeDriver", lambda _cli: scripted)
    return scripted
