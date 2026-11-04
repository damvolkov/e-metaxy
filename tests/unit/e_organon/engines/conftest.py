"""tests/unit/e_organon/engines: the bridge wired to a scripted coder over a real sqlite ledger on a temporary file, and a
`settle` that waits for a task to end."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from e_organon.engines.bridge import BridgeEngine, Task, TaskOrder
from e_organon.infra.config.providers.drivers.store.sqlite import SqliteSettings
from e_organon.ops.projects import NamedProjects
from e_organon.providers.drivers.store.sqlite import SqliteDriver

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from e_organon.ports.coder import Profile
    from support.bridge import Settle, Wire
    from support.coder import ScriptedCoder


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
