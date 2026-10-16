"""Package-wide fixtures: the bridge wired to a scripted coder and a recording notifier over a real ledger."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fakes import DONE_SCRIPT, RecordingNotifier, ScriptedCoder, Settle, Wire

from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.task import Task, TaskOrder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from e_metaxy.adapters.sqlite import SQLiteAdapter
    from e_metaxy.models.profile import Profile


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
