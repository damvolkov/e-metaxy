"""tests/unit/e_organon/services/tekton/start: tekton/start answers at once with the running task; a refusal of the bridge
is the stream's last event."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.tekton import StartIn, TaskOut
from e_organon.ports.coder import CoderKind

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine
    from e_organon.services.tekton.start import StartTektonService
    from support.coder import ScriptedCoder
    from support.flow import Answered, Refused


async def test_start_answers_with_the_running_task(
    start: StartTektonService, answered: Answered, bridge: BridgeEngine, coder: ScriptedCoder
) -> None:
    steps, task = await answered(start, StartIn(prompt="ping", project="/tmp", profile="research"))
    settled = await bridge.status(task.id, wait=2.0)
    assert (steps, isinstance(task, TaskOut), task.state, task.coder, task.profile) == (
        ["order"],
        True,
        "running",
        CoderKind.CLAUDE,
        "research",
    )
    assert (settled.state, settled.result, [spec.prompt for spec in coder.specs]) == ("done", "pong", ["ping"])


async def test_start_continues_a_session(start: StartTektonService, answered: Answered, coder: ScriptedCoder) -> None:
    _, task = await answered(start, StartIn(prompt="go", project="/tmp", session="s-new", fork=True))
    assert (task.parent, task.fork) == ("s-new", True)


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (StartIn(prompt="p", project="/tmp", profile="nope"), "UnknownProfileError"),
        (StartIn(prompt="p", project="/etc", profile="research"), "RootDeniedError"),
        (StartIn(prompt="p", project="/tmp", session="gone"), "UnknownSessionError"),
    ],
    ids=["profile", "root", "session"],
)
async def test_start_refuses_with_the_reason(
    start: StartTektonService, refused: Refused, data: StartIn, kind: str
) -> None:
    assert await refused(start, data) == (["order"], kind)
