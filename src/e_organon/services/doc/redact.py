"""e_organon.services.doc.redact — doc/redact: text, images and metadata taken out of a PDF for good, the copy kept in the outbox.

What is struck is removed, not covered (`ports/redact`): by `terms` — literal or regular expressions — on `pages`, and by
`boxes` as displayed, as `doc/stamp` places things. The copy is the same bytes for the same input, so the content-named outbox
writes it once. `count` says how many strikes it took: zero is a valid answer — the terms were not there — and the copy is
still scrubbed. Three steps: the file read, the strikes made, the copy kept."""

from typing import TYPE_CHECKING

from e_organon.models.doc import RedactIn, RedactOut
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.redact import RedactPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "redact", "keep")


##### TOOL #####
class RedactDocService(ToolFlow[RedactIn, RedactOut]):
    """doc/redact: a PDF with what was struck removed."""

    __slots__ = ("_artifacts", "_files", "_redact")

    def __init__(self, redact: RedactPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._redact = redact
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_run(self, data: RedactIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        done = await self._redact.redact(raw, terms=data.terms, regex=data.regex, boxes=data.boxes, pages=data.pages)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        kept = await self._artifacts.keep(done.data, f"{path.stem}-redacted", ".pdf")
        yield Done(result=RedactOut(path=str(kept), size=len(done.data), count=done.count))
