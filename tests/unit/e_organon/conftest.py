"""tests/unit/e_organon: the live app on the real graph, a request away — `client` over the faked services of `tests/conftest`
(`keys`: `ana` an account, `root` the admin; `ana_key` and `root_key` the `Authorization` headers that carry theirs), and what
the access log wrote, recorded; and what every tekton test runs on: `book`, the profile book; `ledger`, a real sqlite file
on a temporary path; `bridge`, the engine over `coder` (the scripted one of `tests/conftest`), `wire` the builder of more,
`settle` the wait that ends a task."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from e_organon.api import middlewares as middlewares_module
from e_organon.engines.bridge import BridgeEngine, Task, TaskOrder
from e_organon.infra.config.providers.drivers.store.sqlite import SqliteSettings
from e_organon.main import create_app
from e_organon.ops.projects import NamedProjects
from e_organon.ports.coder import Profile
from e_organon.providers.drivers.store.sqlite import SqliteDriver

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping

    from pytest_resources import Resources

    from support.bridge import Settle, Wire
    from support.coder import ScriptedCoder


class RequestLogs:
    """The `request` events the access log writes, fields only — what a test asserts a request was logged with."""

    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def info(self, event: str, **fields: object) -> None:
        _ = event == "request" and self.requests.append(fields)


@pytest.fixture
def request_logs(monkeypatch: pytest.MonkeyPatch) -> RequestLogs:
    """The access log's logger replaced by a recorder for the test's length."""
    recorder = RequestLogs()
    monkeypatch.setattr(middlewares_module, "logger", recorder)
    return recorder


@pytest.fixture
def ana_key() -> dict[str, str]:
    return {"Authorization": "Bearer t-ana"}


@pytest.fixture
def root_key() -> dict[str, str]:
    return {"Authorization": "Bearer t-root"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def book(resources: Resources) -> Mapping[str, Profile]:
    """The tests' profile book: `research`, `code`, `direct`, each admitting `/tmp` alone."""
    return Profile.book((resources.path / "profiles" / "book.yaml").read_bytes())


@pytest.fixture
async def ledger(tmp_path: Path) -> AsyncIterator[SqliteDriver]:
    async with SqliteDriver(SqliteSettings(path=tmp_path / "ledger.db")) as store:
        yield store


@pytest.fixture
def order() -> TaskOrder:
    return TaskOrder(prompt="ping", profile="research", cwd="/tmp")


@pytest.fixture
def wire(ledger: SqliteDriver, book: Mapping[str, Profile]) -> Wire:
    def build(coder: ScriptedCoder, limit: int = 2) -> BridgeEngine:
        return BridgeEngine(
            coders={coder.kind: coder}, ledger=ledger, profiles=book, projects=NamedProjects(Path("/tmp")), limit=limit
        )

    return build


@pytest.fixture
async def bridge(wire: Wire, coder: ScriptedCoder) -> AsyncIterator[BridgeEngine]:
    async with wire(coder) as opened:
        yield opened


@pytest.fixture
def settle() -> Settle:
    async def wait(bridge: BridgeEngine, task: Task) -> Task:
        return await bridge.status(task.id, wait=2.0)

    return wait
