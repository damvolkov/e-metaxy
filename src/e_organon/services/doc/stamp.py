"""e_organon.services.doc.stamp — doc/stamp: an image or a text drawn on a PDF page, kept in the outbox.

`at` says where, in one of three ways resolved here to a page and a box *as displayed* (origin at the visible page's
bottom-left after the page's rotation and crop box): a form field (its widget's rectangle, the image fitted inside), a text
anchor (found by the render port: the stamp starts at its bottom-left corner moved by the offset, as wide as the anchor or
as `width` says), or an explicit box, which is already in those terms. A field's and an anchor's rectangles are the PDF's, in
user space: the page's geometry turns them into the displayed ones. A field the form lacks, or an anchor the pages lack,
fails the run. Four steps: the files read, the place found, the stamp drawn, the PDF kept."""

from typing import TYPE_CHECKING

from e_organon.models.doc import AtAnchor, AtField, FileOut, StampIn
from e_organon.models.error import AnchorNotFoundError, FieldNotFoundError
from e_organon.models.flow import Done, Event, Step
from e_organon.ports.pdf import PageGeometry, PdfBox
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.models.doc import At
    from e_organon.ports.pdf import PdfPort
    from e_organon.ports.render import RenderPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "locate", "stamp", "keep")


##### TOOL #####
class StampDocService(ToolFlow[StampIn, FileOut]):
    """doc/stamp: a stamped copy of a PDF."""

    __slots__ = ("_artifacts", "_files", "_pdf", "_render")

    def __init__(self, pdf: PdfPort, render: RenderPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._pdf = pdf
        self._render = render
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    @staticmethod
    def _events_shown(
        geometry: PageGeometry, rect: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """A user-space rectangle `(left, bottom, right, top)` as displayed: its corner and its size."""
        (x0, y0), (x1, y1) = geometry.shown(rect[0], rect[1]), geometry.shown(rect[2], rect[3])
        return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)

    async def _events_locate(self, raw: bytes, at: At) -> tuple[int, PdfBox]:
        """The page and the box `at` names, as displayed."""
        match at:
            case AtField(field=name):
                match [found for found in (await self._pdf.info(raw)).fields if found.name == name]:
                    case [found, *_]:
                        geometry = (await self._pdf.geometry(raw))[found.page]
                        x, y, width, height = self._events_shown(geometry, found.rect)
                        return found.page, PdfBox(x=x, y=y, width=width, height=height)
                    case _:
                        msg = f"the PDF has no field {name!r}"
                        raise FieldNotFoundError(msg)
            case AtAnchor(anchor=text, occurrence=nth, offset=(dx, dy), width=width):
                match (await self._render.find(raw, text))[nth - 1 : nth]:
                    case [hit]:
                        geometry = (await self._pdf.geometry(raw))[hit.page]
                        x, y, w, h = self._events_shown(geometry, hit.rect)
                        sized = (width, None) if width else (w, h)
                        return hit.page, PdfBox(x=x + dx, y=y + dy, width=sized[0], height=sized[1])
                    case _:
                        msg = f"{text!r} is not on the PDF {nth} time(s)"
                        raise AnchorNotFoundError(msg)
            case box:
                return box.page, PdfBox(x=box.x, y=box.y, width=box.width, height=box.height)

    async def _events_run(self, data: StampIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        picture = None if data.image is None else (await self._files.read(data.image))[1]
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        page, box = await self._events_locate(raw, data.at)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        stamped = await self._pdf.stamp(raw, page, box, image=picture, text=data.text, opacity=data.opacity)
        yield Step(name=STEPS[3], index=3, total=len(STEPS))
        kept = await self._artifacts.keep(stamped, f"{path.stem}-stamped", ".pdf")
        yield Done(result=FileOut(path=str(kept), size=len(stamped)))
