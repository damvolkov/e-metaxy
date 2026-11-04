"""tests/unit/e_organon/services/flow: a workflow streams its steps and ends in an answer — or in why not, never a raise."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.error import FlowError
from e_organon.models.flow import Done, Failed, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.models.flow import Event


class Echo(ToolFlow[str, str]):
    async def _events_run(self, data: str) -> AsyncIterator[Event]:
        yield Step(name="echo", index=0, total=1)
        yield Done(result=data.upper())


class Broken(ToolFlow[str, str]):
    async def _events_run(self, data: str) -> AsyncIterator[Event]:
        yield Step(name="break", index=0, total=1)
        raise ValueError(data)


class Silent(ToolFlow[str, str]):
    async def _events_run(self, data: str) -> AsyncIterator[Event]:
        yield Step(name=data, index=0, total=1)


async def test_flow_streams_steps_then_done() -> None:
    assert [event async for event in Echo().events("ok")] == [Step(name="echo", index=0, total=1), Done(result="OK")]


async def test_flow_run_is_the_answer() -> None:
    assert await Echo().run("ok") == "OK"


async def test_flow_raise_becomes_the_last_event() -> None:
    events = [event async for event in Broken().events("boom")]
    assert events[-1] == Failed(kind="ValueError", reason="boom")


async def test_flow_run_raises_the_streamed_failure() -> None:
    with pytest.raises(FlowError) as caught:
        await Broken().run("boom")
    assert caught.value.failed == Failed(kind="ValueError", reason="boom")


async def test_flow_without_an_answer_fails() -> None:
    with pytest.raises(FlowError, match="EmptyFlow"):
        await Silent().run("x")


async def test_flow_base_has_no_workflow() -> None:
    assert [event async for event in ToolFlow[str, str]().events("x")] == [
        Failed(kind="NotImplementedError", reason="")
    ]
