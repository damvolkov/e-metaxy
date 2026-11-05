"""e_organon.services.organon.find: organon/find — the tools that answer a need, ranked deterministically.

No model, no embeddings: the query and each tool's text are lower-cased words (`[a-z0-9]+`), and a tool scores, for each
query word, 4 when it is a word of the tool's name (`doc_merge`: doc, merge), 2 when of its title, 1 when of its
description — each field counted once per word. The best `TOP` come back, ties by name; a query with no word scores
nothing and lists the section (or every tool) by name. `section` keeps the tools whose name begins with it. One step."""

import heapq
import re
from typing import TYPE_CHECKING, Final

from e_organon.models.flow import Done, Event, Step
from e_organon.models.organon import FindIn, FindOut, Found
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from e_organon.infra.mcp.models import MCPEntry

### how many tools an answer holds: enough to choose from, few enough to read.
TOP: Final[int] = 5
### what a query word earns in a tool's name, title and description.
WEIGHTS: Final[tuple[int, int, int]] = (4, 2, 1)
WORD: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


##### TOOL #####
class FindOrganonService(ToolFlow[FindIn, FindOut]):
    """organon/find: the tools of the door's registry that answer a query."""

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[MCPEntry]) -> None:
        self._tools = tools

    ##### PRIVATE #####

    @staticmethod
    def _events_words(text: str) -> frozenset[str]:
        return frozenset(WORD.findall(text.lower()))

    def _events_score(self, wanted: frozenset[str], entry: MCPEntry) -> int:
        fields = (entry.tool.name, entry.tool.title, entry.tool.description)
        return sum(
            weight * len(wanted & self._events_words(text)) for weight, text in zip(WEIGHTS, fields, strict=True)
        )

    async def _events_run(self, data: FindIn) -> AsyncIterator[Event]:
        yield Step(name="rank", index=0, total=1)
        wanted, section = self._events_words(data.query), data.section.strip().lower()
        scored = [
            (self._events_score(wanted, entry), entry)
            for entry in self._tools
            if section in {"", entry.tool.name.partition("_")[0]}
        ]
        best = heapq.nsmallest(
            TOP, (pair for pair in scored if pair[0] > 0 or not wanted), key=lambda pair: (-pair[0], pair[1].tool.name)
        )
        yield Done(
            result=FindOut(
                tools=[
                    Found(name=entry.tool.name, description=entry.tool.description, schema=entry.arguments)
                    for _, entry in best
                ]
            )
        )
