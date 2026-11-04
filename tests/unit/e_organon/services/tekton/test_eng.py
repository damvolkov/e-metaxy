"""tests/unit/e_organon/services/tekton/eng: the `eng` grammar — every verb parsed from the user's words, each run on the
bridge; a named project that is no project is the order itself."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.tekton import (
    EngIn,
    EngList,
    EngNew,
    EngRead,
    EngRename,
    EngResume,
    EngStatus,
    EngStop,
)
from e_organon.services.tekton.eng import EmptyOrderError, EngTektonService
from support.coder import UUID

if TYPE_CHECKING:
    from e_organon.engines.bridge import BridgeEngine
    from support.bridge import Settle
    from support.coder import ScriptedCoder
    from support.flow import Answered, Refused


@pytest.mark.parametrize(
    ("text", "order"),
    [
        ("eng arregla el VAD", EngNew(project="e-voice", prompt="arregla el VAD")),
        ("ENG: arregla", EngNew(project="e-voice", prompt="arregla")),
        ("arregla el VAD", EngNew(project="e-voice", prompt="arregla el VAD")),
        ("eng e-voice: arregla", EngNew(project="e-voice", prompt="arregla", named=True)),
        ("eng @7b4fb561: sigue", EngResume(ref="7b4fb561", prompt="sigue")),
        ("eng @7b4fb561 sigue", EngResume(ref="7b4fb561", prompt="sigue")),
        ("eng @7b4fb561+: otra vía", EngResume(ref="7b4fb561", prompt="otra vía", fork=True)),
        ("eng @Tools MCP en tools.py: sigue", EngResume(ref="Tools MCP en tools.py", prompt="sigue")),
        ("eng @7b4fb561?", EngRead(ref="7b4fb561")),
        ("eng @7b4fb561 = vad-fix", EngRename(ref="7b4fb561", title="vad-fix")),
        ("eng ls", EngList(project="e-voice")),
        ("eng ls e-organon", EngList(project="e-organon")),
        ("eng ps", EngStatus()),
        ("eng stop 01a1", EngStop(task="01a1")),
        ("engineering is hard", EngNew(project="e-voice", prompt="engineering is hard")),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
async def test_eng_parse(text: str, order: object) -> None:
    assert EngTektonService.parse(text, "e-voice") == order


async def test_eng_parse_empty() -> None:
    with pytest.raises(EmptyOrderError):
        EngTektonService.parse("eng   ")


async def test_eng_empty_order_is_refused(eng: EngTektonService, refused: Refused) -> None:
    assert await refused(eng, EngIn(text="eng")) == (["parse"], "EmptyOrderError")


async def test_eng_resume_runs_in_the_session_directory(
    eng: EngTektonService, answered: Answered, bridge: BridgeEngine, coder: ScriptedCoder, settle: Settle
) -> None:
    steps, answer = await answered(eng, EngIn(text="eng @7b4fb561: sigue", profile="code"))
    await bridge.status(answer.result.id, wait=2.0)
    assert (steps, answer.verb, answer.result.state, [(s.session, s.prompt) for s in coder.specs]) == (
        ["parse", "run"],
        "resume",
        "running",
        [(UUID, "sigue")],
    )


async def test_eng_new_starts_a_task_in_the_project(
    eng: EngTektonService, answered: Answered, bridge: BridgeEngine, coder: ScriptedCoder
) -> None:
    _, answer = await answered(eng, EngIn(text="eng arregla", project="/tmp"))
    await bridge.status(answer.result.id, wait=2.0)
    assert (answer.verb, [(s.cwd, s.prompt) for s in coder.specs]) == ("new", [("/tmp", "arregla")])


async def test_eng_named_project_that_is_no_project_is_the_order(
    eng: EngTektonService, answered: Answered, bridge: BridgeEngine, coder: ScriptedCoder
) -> None:
    _, answer = await answered(eng, EngIn(text="eng nota: compra pan", project="/tmp"))
    await bridge.status(answer.result.id, wait=2.0)
    assert (answer.verb, coder.specs[0].prompt, coder.specs[0].cwd) == ("new", "nota: compra pan", "/tmp")


@pytest.mark.parametrize(
    ("text", "verb"),
    [("eng @7b4fb561?", "read"), ("eng @7b4fb561 = x", "rename"), ("eng ls /tmp", "list"), ("eng ps", "status")],
)
async def test_eng_verbs(eng: EngTektonService, answered: Answered, text: str, verb: str) -> None:
    _, answer = await answered(eng, EngIn(text=text))
    assert answer.verb == verb


async def test_eng_ps_lists_tasks_as_their_wire_shape(
    eng: EngTektonService, answered: Answered, bridge: BridgeEngine, settle: Settle
) -> None:
    _, started = await answered(eng, EngIn(text="eng /tmp: go"))
    await bridge.status(started.result.id, wait=2.0)
    _, answer = await answered(eng, EngIn(text="eng ps"))
    assert [task.id for task in answer.result] == [started.result.id]


async def test_eng_stop(eng: EngTektonService, answered: Answered, bridge: BridgeEngine) -> None:
    _, started = await answered(eng, EngIn(text="eng /tmp: go"))
    await bridge.status(started.result.id, wait=2.0)
    _, answer = await answered(eng, EngIn(text=f"eng stop {started.result.id}"))
    assert (answer.verb, answer.result.state) == ("stop", "done")
