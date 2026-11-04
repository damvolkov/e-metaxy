"""e_organon.services.tekton.eng: tekton/eng — the `eng` grammar, parsed without a model and run on the bridge.

One grammar for every front: the words arrive as the user typed them (with or without the `eng` prefix), the first rule
whose pattern matches the whole order builds its variant, and the bridge runs that variant. A `project:` that names no
project is part of the order, not an error: `eng nota: …` is a prompt.

    eng [project:] <order>        a new session          eng @ref?              where it stopped
    eng @ref: <order>             continue it            eng @ref = <title>     rename it
    eng @ref+: <order>            branch it              eng ls [project]       sessions
    eng ps                        tasks                  eng stop <task>        interrupt"""

import re
from typing import TYPE_CHECKING, Any, Final

import anyio

from e_organon.engines.bridge import Task, TaskOrder
from e_organon.infra.errors import ServiceError
from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import (
    EngIn,
    EngList,
    EngNew,
    EngOrder,
    EngOut,
    EngRead,
    EngRename,
    EngResume,
    EngStatus,
    EngStop,
    TaskOut,
)
from e_organon.ops.projects import UnknownProjectError
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from e_organon.engines.bridge import BridgeEngine
    from e_organon.ops.projects import NamedProjects

STEPS: tuple[str, ...] = ("parse", "run")
PREFIX: Final = re.compile(r"\s*eng\b[\s:]*", re.IGNORECASE)
REF: Final = r"@(?P<ref>[^?+=:]+?)\s*"
RULES: Final[tuple[tuple[re.Pattern[str], Callable[[re.Match[str], str], EngOrder]], ...]] = (
    (re.compile(r"ps", re.IGNORECASE), lambda _m, _p: EngStatus()),
    (re.compile(r"ls(?:\s+(?P<project>\S+))?", re.IGNORECASE), lambda m, p: EngList(project=m["project"] or p)),
    (re.compile(r"stop\s+(?P<task>\S+)", re.IGNORECASE), lambda m, _p: EngStop(task=m["task"])),
    (re.compile(REF + r"\?"), lambda m, _p: EngRead(ref=m["ref"])),
    (
        re.compile(REF + r"=\s*(?P<title>.+)", re.DOTALL),
        lambda m, _p: EngRename(ref=m["ref"], title=m["title"].strip()),
    ),
    (
        re.compile(REF + r"(?P<fork>\+)?\s*:\s*(?P<prompt>.+)", re.DOTALL),
        lambda m, _p: EngResume(ref=m["ref"], prompt=m["prompt"].strip(), fork=bool(m["fork"])),
    ),
    (
        re.compile(r"@(?P<ref>[^\s?+=:]+)(?P<fork>\+)?\s+(?P<prompt>.+)", re.DOTALL),
        lambda m, _p: EngResume(ref=m["ref"], prompt=m["prompt"].strip(), fork=bool(m["fork"])),
    ),
    (
        re.compile(r"(?P<project>[\w.-]+)\s*:\s*(?P<prompt>.+)", re.DOTALL),
        lambda m, _p: EngNew(project=m["project"], prompt=m["prompt"].strip(), named=True),
    ),
    (re.compile(r"(?P<prompt>.+)", re.DOTALL), lambda m, p: EngNew(project=p, prompt=m["prompt"].strip())),
)


##### ERRORS #####
class EmptyOrderError(ServiceError):
    """An `eng` order with nothing after the prefix."""

    def __init__(self) -> None:
        super().__init__("empty order; try `eng <project>: <order>`, `eng @<session>: <order>`, `eng ls` or `eng ps`")


##### TOOL #####
class EngTektonService(ToolFlow[EngIn, EngOut]):
    """tekton/eng: an `eng` order parsed and run on the bridge; the answer says which verb ran."""

    __slots__ = ("_bridge", "_projects")

    def __init__(self, bridge: BridgeEngine, projects: NamedProjects) -> None:
        self._bridge = bridge
        self._projects = projects

    ##### PRIVATE #####

    @staticmethod
    def _events_body(text: str) -> str:
        """The words after a leading `eng`, or all of them when the front already dropped it."""
        return text[found.end() :].strip() if (found := PREFIX.match(text)) else text.strip()

    @classmethod
    def _events_wire(cls, answer: object) -> Any:
        """What the bridge answered, as the wire shape: a task as `TaskOut`, a list of them one by one."""
        match answer:
            case Task():
                return TaskOut.of(answer)
            case list():
                return [cls._events_wire(each) for each in answer]
            case _:
                return answer

    async def _events_new(self, order: EngNew, text: str, data: EngIn) -> Task:
        """A named project that does not exist was never a project: the whole text is the order."""
        project, prompt = order.project, order.prompt
        try:
            _ = order.named and await anyio.to_thread.run_sync(self._projects.resolve, project)
        except UnknownProjectError:
            project, prompt = data.project, text
        return await self._bridge.start(TaskOrder(prompt=prompt, profile=data.profile, cwd=project))

    async def _events_resume(self, order: EngResume, data: EngIn) -> Task:
        """The continued session runs in the directory it lives in."""
        session = await self._bridge.read(order.ref, last=0)
        return await self._bridge.start(
            TaskOrder(
                prompt=order.prompt,
                profile=data.profile,
                cwd=session.session.cwd or data.project,
                session=session.session.session,
                fork=order.fork,
            )
        )

    async def _events_run(self, data: EngIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        order = self.parse(data.text, data.project)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        bridge = self._bridge
        match order:
            case EngNew():
                answer = await self._events_new(order, self._events_body(data.text), data)
            case EngResume():
                answer = await self._events_resume(order, data)
            case EngRead(ref=ref):
                answer = await bridge.read(ref)
            case EngRename(ref=ref, title=title):
                answer = await bridge.update(ref, title=title)
            case EngList(project=listed):
                answer = await bridge.find(listed)
            case EngStatus():
                answer = await bridge.tasks(limit=10)
            case _:
                answer = await bridge.cancel(order.task)
        yield Done(result=EngOut(verb=str(order.__struct_config__.tag), result=self._events_wire(answer)))

    ############################################################

    ##### PUBLIC #####

    @classmethod
    def parse(cls, text: str, project: str = "") -> EngOrder:
        """The order the words say; `project` is the caller's guess for an order that names none."""
        body = cls._events_body(text)
        match next((build(m, project) for pattern, build in RULES if (m := pattern.fullmatch(body))), None):
            case None:
                raise EmptyOrderError
            case order:
                return order
