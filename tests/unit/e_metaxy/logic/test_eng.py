from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fakes import UUID

from e_metaxy.logic.eng import EngDesk
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.eng import EngList, EngNew, EngRead, EngRename, EngResume, EngStatus, EngStop
from e_metaxy.models.error import EmptyOrderError

if TYPE_CHECKING:
    from e_metaxy.logic.bridge import Bridge


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
        ("eng ls e-metaxy", EngList(project="e-metaxy")),
        ("eng ps", EngStatus()),
        ("eng stop 01a1", EngStop(task="01a1")),
        ("engineering is hard", EngNew(project="e-voice", prompt="engineering is hard")),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_eng_parse(text: str, order: object) -> None:
    assert EngDesk.parse(text, "e-voice") == order


def test_eng_parse_empty() -> None:
    with pytest.raises(EmptyOrderError):
        EngDesk.parse("eng   ")


@pytest.fixture
def desk(bridge: Bridge) -> EngDesk:
    return EngDesk(bridge, ProjectIndex(Path("/tmp")))


async def test_eng_resume_runs_in_the_session_directory(desk: EngDesk, coder, settle) -> None:
    verb, task = await desk.run("eng @7b4fb561: sigue", profile="code", caller="openhuman")
    await settle(desk._bridge, task)
    assert (verb, [(s.session, s.prompt) for s in coder.specs], task.caller) == (
        "resume",
        [(UUID, "sigue")],
        "openhuman",
    )


async def test_eng_named_project_that_is_no_project_is_the_order(desk: EngDesk, coder, settle) -> None:
    verb, task = await desk.run("eng nota: compra pan", project="/tmp")
    await settle(desk._bridge, task)
    assert (verb, coder.specs[0].prompt, coder.specs[0].cwd) == ("new", "nota: compra pan", "/tmp")


@pytest.mark.parametrize(
    ("text", "verb"),
    [("eng @7b4fb561?", "read"), ("eng @7b4fb561 = x", "rename"), ("eng ls /tmp", "list"), ("eng ps", "status")],
)
async def test_eng_verbs(desk: EngDesk, text: str, verb: str) -> None:
    assert (await desk.run(text))[0] == verb


async def test_eng_stop(desk: EngDesk, settle) -> None:
    _, task = await desk.run("eng /tmp: go")
    await settle(desk._bridge, task)
    assert (await desk.run(f"eng stop {task.id}"))[0] == "stop"
