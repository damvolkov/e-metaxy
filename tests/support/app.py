"""tests/support/app: the services behind the live app, faked — Postgres from the scripted pool of
`support.psqlpy`, the accounts and keys from the dicts of `support.auth`, the coder a script of `support.coder`, the durable queue down (`support.queue`) — no
Claude Code is ever spawned. Every tier's conftest takes these fixtures."""

from types import MappingProxyType

import pytest

from e_organon.api.lifespan import engines as engines_module
from e_organon.api.lifespan import providers as providers_module
from e_organon.infra.auth.models import Role
from e_organon.infra.config.engines import QueueEngine
from e_organon.providers.drivers.database import psqlpy as psqlpy_module
from support.auth import FakeAuth
from support.coder import ScriptedCoder
from support.psqlpy import FakePsqlpyServer
from support.queue import FakeQueue, FakeQueueDatabase


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


@pytest.fixture(autouse=True)
def queue(monkeypatch: pytest.MonkeyPatch) -> FakeQueue:
    """The durable queue the dispatch prefers: down, so jobs run in memory; `queue.up = True` before the app starts
    makes it the one that records what is bound and enqueued."""
    held = FakeQueue()
    monkeypatch.setattr(engines_module, "QUEUES", MappingProxyType({QueueEngine.PGQUEUER: lambda _database: held}))
    return held


@pytest.fixture(autouse=True)
def queue_database(monkeypatch: pytest.MonkeyPatch) -> type[FakeQueueDatabase]:
    """The queue's database where the lifespan would connect asyncpg: one that opens and answers, holding nothing."""
    monkeypatch.setattr(providers_module, "AsyncpgDriver", FakeQueueDatabase)
    return FakeQueueDatabase
