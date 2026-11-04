"""tests/unit/e_organon: the live app on the real graph, a request away — `client` over the faked services of `tests/conftest`
(`keys`: `ana` an account, `root` the admin; `ana_key` and `root_key` the `Authorization` headers that carry theirs), and what
the access log wrote, recorded; and `book`, the profile book every tekton test runs under."""

from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from e_organon.api import middlewares as middlewares_module
from e_organon.main import create_app
from e_organon.ports.coder import Profile

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pytest_resources import Resources


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
