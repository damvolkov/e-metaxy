"""e_organon.services.doc.sign — doc/sign: a PDF signed with the deployment's key, in PAdES.

The key is the provider's (a PKCS#12 named by the settings, never by a request). The signature is invisible unless `at`
is given: then its appearance is drawn first by the tools that already draw — `doc/stamp` for an image or a text,
`doc/signature` for a photographed signature — and the cryptographic signature seals the PDF with it on, so a later change
to the appearance breaks the signature. Four steps: the file read, the appearance drawn (or not), the PDF signed, the
copy kept. A failure of the appearance is the run's, as it is."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut, SignatureIn, SignIn, StampIn
from e_organon.models.error import FlowError
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.sign import SignPort
    from e_organon.services.doc.signature import SignatureDocService
    from e_organon.services.doc.stamp import StampDocService
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "appear", "sign", "keep")


##### TOOL #####
class SignDocService(ToolFlow[SignIn, FileOut]):
    """doc/sign: the PDF, signed."""

    __slots__ = ("_artifacts", "_files", "_sign", "_signature", "_stamp")

    def __init__(
        self,
        sign: SignPort,
        stamp: StampDocService,
        signature: SignatureDocService,
        files: AllowedFiles,
        artifacts: ArtifactEngine,
    ) -> None:
        self._sign = sign
        self._stamp, self._signature = stamp, signature
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_appear(self, data: SignIn) -> FileOut | None:
        """The PDF with its appearance drawn, as the tool that draws it left it in the outbox; none when invisible."""
        match data.at:
            case None:
                return None
            case at:
                match data.photo:
                    case str() as photo:
                        return await self._signature.run(
                            SignatureIn(path=data.path, photo=photo, at=at, lines=data.lines)
                        )
                    case _:
                        return await self._stamp.run(StampIn(path=data.path, at=at, image=data.image, text=data.text))

    async def _events_run(self, data: SignIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        try:
            drawn = await self._events_appear(data)
        except FlowError as error:
            yield error.failed
            return
        ready = raw if drawn is None else (await self._files.read(drawn.path))[1]
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        signed = await self._sign.sign(ready)
        yield Step(name=STEPS[3], index=3, total=len(STEPS))
        kept = await self._artifacts.keep(signed, f"{path.stem}-signed", ".pdf")
        yield Done(result=FileOut(path=str(kept), size=len(signed)))
