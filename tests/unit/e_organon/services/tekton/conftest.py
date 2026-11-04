"""tests/unit/e_organon/services/tekton: each tekton tool over the bridge of `tests/unit/e_organon/conftest` (a scripted coder,
a real ledger), and a tool's run read as `answered` or `refused`."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from e_organon.models.flow import Done, Failed, Step
from e_organon.ops.projects import NamedProjects
from e_organon.services.tekton.cancel import CancelTektonService
from e_organon.services.tekton.catalog import CatalogTektonService
from e_organon.services.tekton.eng import EngTektonService
from e_organon.services.tekton.find import FindTektonService
from e_organon.services.tekton.peers import PeersTektonService
from e_organon.services.tekton.read import ReadTektonService
from e_organon.services.tekton.send import SendTektonService
from e_organon.services.tekton.start import StartTektonService
from e_organon.services.tekton.status import StatusTektonService
from e_organon.services.tekton.tasks import TasksTektonService
from e_organon.services.tekton.update import UpdateTektonService

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine
    from e_organon.services.flow import ToolFlow
    from support.flow import Answered, Refused


@pytest.fixture
def answered() -> Answered:
    """A tool's run as the names of its steps and its answer — `Done`'s result, the run having succeeded."""

    async def run(tool: ToolFlow[Any, Any], data: Any) -> tuple[list[str], Any]:
        events = [event async for event in tool.events(data)]
        match events[-1]:
            case Done(result=result):
                return [event.name for event in events if isinstance(event, Step)], result
            case other:
                pytest.fail(f"no answer: {other!r}")

    return run


@pytest.fixture
def refused() -> Refused:
    """A tool's run as the names of its steps and the kind of the error it failed with."""

    async def run(tool: ToolFlow[Any, Any], data: Any) -> tuple[list[str], str]:
        events = [event async for event in tool.events(data)]
        match events[-1]:
            case Failed(kind=kind):
                return [event.name for event in events if isinstance(event, Step)], kind
            case other:
                pytest.fail(f"not refused: {other!r}")

    return run


@pytest.fixture
def eng(bridge: BridgeEngine) -> EngTektonService:
    return EngTektonService(bridge, NamedProjects(Path("/tmp")))


@pytest.fixture
def start(bridge: BridgeEngine) -> StartTektonService:
    return StartTektonService(bridge)


@pytest.fixture
def status(bridge: BridgeEngine) -> StatusTektonService:
    return StatusTektonService(bridge)


@pytest.fixture
def tasks(bridge: BridgeEngine) -> TasksTektonService:
    return TasksTektonService(bridge)


@pytest.fixture
def cancel(bridge: BridgeEngine) -> CancelTektonService:
    return CancelTektonService(bridge)


@pytest.fixture
def catalog(bridge: BridgeEngine) -> CatalogTektonService:
    return CatalogTektonService(bridge)


@pytest.fixture
def find(bridge: BridgeEngine) -> FindTektonService:
    return FindTektonService(bridge)


@pytest.fixture
def read(bridge: BridgeEngine) -> ReadTektonService:
    return ReadTektonService(bridge)


@pytest.fixture
def update(bridge: BridgeEngine) -> UpdateTektonService:
    return UpdateTektonService(bridge)


@pytest.fixture
def peers(bridge: BridgeEngine) -> PeersTektonService:
    return PeersTektonService(bridge)


@pytest.fixture
def send(bridge: BridgeEngine) -> SendTektonService:
    return SendTektonService(bridge)
