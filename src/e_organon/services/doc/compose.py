"""e_organon.services.doc.compose: doc/compose — a typst template and its data composed into a PDF/A, kept in the outbox.

A template is named (`invoice`: `<name>.typ` in the first of the template folders that holds it — the deployment's, under
`<ORGANON_DATA>/doc/templates`, then the shipped ones) or is a path under the roots. It may read files in its own folder and
nowhere else. The same template and data are the same bytes, so the content-named outbox writes them once. Three steps:
the template found, the PDF composed, the PDF kept."""

import re
from typing import TYPE_CHECKING, Final

import anyio

from e_organon.models.doc import ComposeIn, FileOut
from e_organon.models.error import TemplateNotFoundError
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.compose import ComposePort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "compose", "keep")
### a bare word is a name; anything else (a slash, a dot) is a path.
NAME: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]+")


##### TOOL #####
class ComposeDocService(ToolFlow[ComposeIn, FileOut]):
    """doc/compose: a PDF from a template and its data."""

    __slots__ = ("_artifacts", "_compose", "_files", "_folders")

    def __init__(
        self, compose: ComposePort, files: AllowedFiles, artifacts: ArtifactEngine, *, folders: tuple[Path, ...]
    ) -> None:
        self._compose = compose
        self._files = files
        self._artifacts = artifacts
        self._folders = folders

    ##### PRIVATE #####

    async def _events_template(self, template: str) -> tuple[Path, bytes]:
        """The template's file and source: by name from the folders, else by path under the roots."""
        match NAME.fullmatch(template):
            case None:
                return await self._files.read(template)
            case _:
                candidates = [folder.expanduser() / f"{template}.typ" for folder in self._folders]
                match [each for each in candidates if await anyio.Path(each).is_file()]:
                    case [first, *_]:
                        return first, await anyio.Path(first).read_bytes()
                    case _:
                        msg = f"no template {template!r} in {', '.join(str(folder) for folder in self._folders)}"
                        raise TemplateNotFoundError(msg)

    async def _events_run(self, data: ComposeIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, source = await self._events_template(data.template)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        pdf = await self._compose.compose(source, data.data, path.parent)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        kept = await self._artifacts.keep(pdf, path.stem, ".pdf")
        yield Done(result=FileOut(path=str(kept), size=len(pdf)))
