"""tests/unit/e_organon/services/doc/convert: doc/convert over the real DocProcessor — a Markdown file read whole by
anytomd, two steps then the answer; a path outside the roots fails at the first step."""

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import pytest

from e_organon.models.doc import ConvertIn, ConvertOut
from e_organon.models.flow import Done, Failed, Step
from e_organon.processors.doc import DocProcessor
from e_organon.providers.adapters.markdown.anytomd import AnytomdAdapter
from e_organon.providers.adapters.pages.liteparse import LiteparseAdapter
from e_organon.services.doc.convert import ConvertDocService
from e_organon.services.files import AllowedFiles

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
async def service(tmp_path: Path) -> AsyncIterator[ConvertDocService]:
    async with AsyncExitStack() as stack:
        markdown = await stack.enter_async_context(AnytomdAdapter())
        pages = await stack.enter_async_context(LiteparseAdapter())
        yield ConvertDocService(DocProcessor(markdown, pages), AllowedFiles((tmp_path,)))


async def test_convert_reads_a_document(service: ConvertDocService, tmp_path: Path) -> None:
    (tmp_path / "plan.md").write_text("# Plan\n\nStep one.\n")
    events = [event async for event in service.events(ConvertIn(path=str(tmp_path / "plan.md")))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "read"]
    match events[-1]:
        case Done(result=ConvertOut(name=name, markdown=markdown)):
            assert (name, "Step one." in markdown) == ("plan.md", True)
        case other:
            pytest.fail(f"no answer: {other!r}")


async def test_convert_refuses_outside_the_roots(service: ConvertDocService) -> None:
    events = [event async for event in service.events(ConvertIn(path="/etc/hostname"))]
    match events:
        case [Step(name="resolve"), Failed(kind=kind)]:
            assert kind == "OutsideRootsError"
        case other:
            pytest.fail(f"unexpected events: {other!r}")
