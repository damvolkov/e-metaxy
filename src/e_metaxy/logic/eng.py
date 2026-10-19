"""e_metaxy.logic.eng: the `eng` grammar, parsed without a model and run on the bridge.

One grammar for every front: the words arrive as the user typed them (with or without the `eng` prefix), the
first rule whose pattern matches the whole order builds its variant, and the desk runs that variant on the
bridge. A `project:` that names no project is part of the order, not an error: `eng nota: …` is a prompt.

    eng [project:] <order>        a new session          eng @ref?              where it stopped
    eng @ref: <order>             continue it            eng @ref = <title>     rename it
    eng @ref+: <order>            branch it              eng ls [project]       sessions
    eng ps                        tasks                  eng stop <task>        interrupt"""

import re
from collections.abc import Callable
from typing import Any, Final

import anyio
from beartype import beartype

from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.eng import EngList, EngNew, EngOrder, EngRead, EngRename, EngResume, EngStatus, EngStop
from e_metaxy.models.error import EmptyOrderError, UnknownProjectError
from e_metaxy.models.task import TaskOrder

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


@beartype
class EngDesk:
    """Parses an `eng` order and runs it on the bridge; the answer says which verb ran."""

    __slots__ = ("_bridge", "_projects")

    def __init__(self, bridge: Bridge, projects: ProjectIndex) -> None:
        self._bridge = bridge
        self._projects = projects

    ##### PRIVATE METHODS #####

    @staticmethod
    def _common_body(text: str) -> str:
        """The words after a leading `eng`, or all of them when the front already dropped it."""
        return text[found.end() :].strip() if (found := PREFIX.match(text)) else text.strip()

    async def _run_new(self, order: EngNew, text: str, inferred: str, profile: str, caller: str) -> Any:
        """A named project that does not exist was never a project: the whole text is the order."""
        project, prompt = order.project, order.prompt
        try:
            _ = order.named and await anyio.to_thread.run_sync(self._projects.resolve, project)
        except UnknownProjectError:
            project, prompt = inferred, text
        return await self._bridge.start(TaskOrder(prompt=prompt, profile=profile, cwd=project, caller=caller))

    ############################################################

    ##### PUBLIC #####

    @classmethod
    def parse(cls, text: str, project: str = "") -> EngOrder:
        """The order the words say; `project` is the caller's guess for an order that names none."""
        body = cls._common_body(text)
        match next((build(m, project) for pattern, build in RULES if (m := pattern.fullmatch(body))), None):
            case None:
                raise EmptyOrderError
            case order:
                return order

    async def run(self, text: str, project: str = "", profile: str = "code", caller: str = "") -> tuple[str, Any]:
        """The verb that ran and what it answered."""
        order = self.parse(text, project)
        bridge = self._bridge
        match order:
            case EngNew():
                answer = await self._run_new(order, self._common_body(text), project, profile, caller)
            case EngResume(ref=ref, prompt=prompt, fork=fork):
                session = await bridge.read(ref, last=0)
                answer = await bridge.start(
                    TaskOrder(
                        prompt=prompt,
                        profile=profile,
                        cwd=session.session.cwd or project,
                        session=session.session.session,
                        fork=fork,
                        caller=caller,
                    )
                )
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
        return str(order.__struct_config__.tag), answer
