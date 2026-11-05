"""e_organon.services.doc.signature — doc/signature: a photographed signature placed on a PDF, visually.

Two tools composed, not copied: `image/cutout` lifts the ink off the photo, `doc/stamp` draws the PNG it made where `at`
says. The stream is theirs one after the other — the cutout's steps (`cutout.…`) then the stamp's (`stamp.…`), numbered as
one run —, a failure in either is the run's, and the answer is the stamped PDF. Not a cryptographic signature."""

from typing import TYPE_CHECKING, Any

from e_organon.models.doc import FileOut, SignatureIn, StampIn
from e_organon.models.flow import Done, Event, Step
from e_organon.models.image import CutoutIn
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.services.doc.stamp import StampDocService
    from e_organon.services.image.cutout import CutoutImageService

PARTS: tuple[tuple[str, int], ...] = (("cutout", 4), ("stamp", 4))


##### TOOL #####
class SignatureDocService(ToolFlow[SignatureIn, FileOut]):
    """doc/signature: the PDF with the photographed signature on it."""

    __slots__ = ("_cutout", "_stamp")

    def __init__(self, cutout: CutoutImageService, stamp: StampDocService) -> None:
        self._cutout = cutout
        self._stamp = stamp

    ##### PRIVATE #####

    @staticmethod
    async def _events_relay(
        events: AsyncIterator[Event], part: str, offset: int, sink: list[Any]
    ) -> AsyncIterator[Event]:
        """A tool's events as this run's: its steps renamed `<part>.<step>` and numbered after `offset`, its failure
        as it is; its answer is not an event here, it goes into `sink`."""
        total = sum(count for _, count in PARTS)
        async for event in events:
            match event:
                case Step():
                    yield Step(name=f"{part}.{event.name}", index=offset + event.index, total=total)
                case Done(result=result):
                    sink.append(result)
                case failed:
                    yield failed

    async def _events_run(self, data: SignatureIn) -> AsyncIterator[Event]:
        cut: list[FileOut] = []
        async for event in self._events_relay(
            self._cutout.events(CutoutIn(path=data.photo, color=data.color)), "cutout", 0, cut
        ):
            yield event
        stamped: list[FileOut] = []
        match cut:
            case [ink]:
                order = StampIn(path=data.path, image=ink.path, at=data.at)
                async for event in self._events_relay(self._stamp.events(order), "stamp", PARTS[0][1], stamped):
                    yield event
        match stamped:
            case [signed]:
                yield Done(result=signed)
