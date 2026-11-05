"""tests/unit/e_organon/api/lifespan/db: every database the settings name, provisioned in order; a failure only warns."""

from typing import ClassVar

import pytest
from litestar import Litestar
from pydantic import PostgresDsn, Secret

from e_organon.api.lifespan import db
from e_organon.infra.errors import DatabaseError


class FakeDriver:
    """A postgres driver whose `provision` logs the DSN it was built over: created unless the name ends in `down`,
    refused when it does."""

    log: ClassVar[list[str]] = []

    def __init__(self, *, dsn: Secret[PostgresDsn], **_: object) -> None:
        self.dsn = str(dsn.get_secret_value())

    async def provision(self) -> bool:
        self.log.append(self.dsn)
        match self.dsn.endswith("down"):
            case True:
                msg = "unreachable"
                raise DatabaseError(msg)
            case False:
                return True


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> type[FakeDriver]:
    FakeDriver.log = []
    monkeypatch.setattr(db, "PsqlpyDriver", FakeDriver)
    return FakeDriver


async def test_db_provisions_every_row(fake: type[FakeDriver]) -> None:
    async with db.lifespan(Litestar()):
        assert fake.log == [str(dsn.get_secret_value()) for dsn in db.databases().values()]


async def test_db_failure_warns(fake: type[FakeDriver]) -> None:
    """A database that cannot be provisioned reads as not created; startup goes on."""
    assert await db.provision("app", Secret(PostgresDsn("postgresql://h:1/down"))) is False
    assert await db.provision("app", Secret(PostgresDsn("postgresql://h:1/up"))) is True


def test_db_rows_are_the_service_and_its_queue() -> None:
    """The service's own database (POSTGRES_DSN) and the queue's, apart (QUEUE_DSN): one row each."""
    assert list(db.databases()) == ["app", "queue"]


def test_db_defaults_name_the_organon_databases() -> None:
    """Organon's data in `organon`, its jobs in `organon_background` on the local ParadeDB."""
    named = {concern: str(dsn.get_secret_value()) for concern, dsn in db.databases().items()}
    assert (named["app"], named["queue"]) == (
        "postgresql://postgres:postgres@127.0.0.1:45011/organon",
        "postgresql://postgres:postgres@127.0.0.1:45011/organon_background",
    )
