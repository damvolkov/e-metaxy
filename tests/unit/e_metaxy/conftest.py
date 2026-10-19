"""Package-wide fixtures: the bridge wired to a scripted coder and a recording notifier over a real ledger, and
the live app on the real graph — env seeded before the lazy core singletons ever load.

`os.environ` stays untouched at module import; the seeding rides `pytest_configure`, which pytest runs before
collection — the earliest point a test module touches the settings proxy. External env wins."""

import asyncio
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx2
import pytest
from fakes import BASE, DONE_SCRIPT, PASSPHRASE, SECRET, RecordingNotifier, ScriptedCoder, Settle, Wire, lifespan

from e_metaxy.core.crypto import Crypto
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.crypto import CryptoSettings
from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.main import create_app
from e_metaxy.models.task import Task, TaskOrder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping

    from litestar import Litestar

    from e_metaxy.adapters.sqlite import SQLiteAdapter
    from e_metaxy.models.profile import Profile

RESOURCES = Path(__file__).resolve().parents[2] / "resources"


def pytest_configure() -> None:
    """Seed the app's env once per process: signing key, owner, issuer, profile book, a private ledger and a
    fake `claude` whose `mcp serve` is the stand-in server, run by this interpreter."""
    home = Path(tempfile.mkdtemp(prefix="e-metaxy-tests-"))
    binary = home / "claude"
    binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{RESOURCES / "bin" / "claude.py"}" "$@"\n')
    binary.chmod(0o755)
    hashed = asyncio.run(Crypto(CryptoSettings(secret=Secret(SECRET))).hash_password(PASSPHRASE))
    seeds = {
        "CRYPTO__SECRET": SECRET,
        "METAXY_AUTH_ISSUER": BASE,
        "METAXY_AUTH_OWNER_HASH": hashed,
        "METAXY_PROFILES": str(RESOURCES / "profiles" / "book.yaml"),
        "METAXY_LEDGER": str(home / "ledger.db"),
        "METAXY_CLAUDE": str(binary),
    }
    _ = [os.environ.setdefault(key, value) for key, value in seeds.items()]


@pytest.fixture
def coder() -> ScriptedCoder:
    return ScriptedCoder(DONE_SCRIPT)


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def order() -> TaskOrder:
    return TaskOrder(prompt="ping", profile="research", cwd="/tmp", caller="openhuman")


@pytest.fixture
def wire(ledger: SQLiteAdapter, book: Mapping[str, Profile], notifier: RecordingNotifier) -> Wire:
    def build(coder: ScriptedCoder, limit: int = 2) -> Bridge:
        return Bridge(
            coders={coder.kind: coder},
            notifiers={notifier.name: notifier},
            ledger=ledger,
            profiles=book,
            projects=ProjectIndex(Path("/tmp")),
            limit=limit,
        )

    return build


@pytest.fixture
async def bridge(wire: Wire, coder: ScriptedCoder) -> AsyncIterator[Bridge]:
    async with wire(coder) as opened:
        yield opened


@pytest.fixture
def settle() -> Settle:
    async def wait(bridge: Bridge, task: Task) -> Task:
        return await bridge.status(task.id, wait=2.0)

    return wait


@pytest.fixture
async def app() -> AsyncIterator[Litestar]:
    """The assembled app with its lifespan chain run: every section built, the graph sealed."""
    built = create_app()
    async with lifespan(built):
        yield built


@pytest.fixture
async def http(app: Litestar) -> AsyncIterator[httpx2.AsyncClient]:
    ### litestar types its scope as its own union, httpx2 as the asgiref one: the same protocol, two spellings.
    transport = httpx2.ASGITransport(cast("Any", app))
    async with httpx2.AsyncClient(transport=transport, base_url=BASE) as client:
        yield client


@pytest.fixture
def bearer(app: Litestar) -> Callable[[str], dict[str, str]]:
    """An access token the live authority accepts, minted by the live crypto engine for the given scopes."""

    def make(scopes: str) -> dict[str, str]:
        services = app.state.system.services
        claims = {
            "iss": services.policy.issuer,
            "aud": services.policy.resource,
            "sub": "owner",
            "client_id": "tests",
            "scope": scopes,
        }
        token = services.crypto.create_token(claims, expires_in=timedelta(minutes=5))
        return {"authorization": f"Bearer {token}"}

    return make
