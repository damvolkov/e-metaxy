"""tests/support/tools: canonical tools of the tests' own — one that answers in two steps, one that fails after a step,
one that never ends — what the job tests register as kinds."""

from typing import TYPE_CHECKING, Any

import anyio
import msgspec

from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from e_organon.infra.background import BackgroundReporter


class WordIn(msgspec.Struct, frozen=True, kw_only=True):
    text: str


class WordOut(msgspec.Struct, frozen=True, kw_only=True):
    shouted: str


class ShoutTool(ToolFlow[WordIn, WordOut]):
    """Two steps, then the text upper-cased."""

    async def _events_run(self, data: WordIn) -> AsyncIterator[Event]:
        yield Step(name="read", index=0, total=2)
        yield Step(name="shout", index=1, total=2)
        yield Done(result=WordOut(shouted=data.text.upper()))


class BoomTool(ToolFlow[WordIn, WordOut]):
    """One step, then a raise."""

    async def _events_run(self, data: WordIn) -> AsyncIterator[Event]:
        yield Step(name="read", index=0, total=1)
        raise ValueError(data.text)


class SlowTool(ToolFlow[WordIn, WordOut]):
    """One step, then it waits for ever, until cancelled."""

    async def _events_run(self, data: WordIn) -> AsyncIterator[Event]:
        yield Step(name="read", index=0, total=1)
        await anyio.sleep_forever()
        yield Done(result=WordOut(shouted=""))


async def crash(args: Mapping[str, Any], report: BackgroundReporter) -> None:
    msg = "worker lost"
    raise RuntimeError(msg)
