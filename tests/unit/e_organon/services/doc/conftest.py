"""tests/unit/e_organon/services/doc: the doc tools over the real in-process adapters — a temporary vault for roots, its
outbox inside it, and a form and a blank PDF placed there."""

from typing import TYPE_CHECKING

import anyio
import pytest

from e_organon.api.lifespan.services import TEMPLATES
from e_organon.engines.artifact import ArtifactEngine
from e_organon.models.doc import FileOut, StampIn
from e_organon.models.flow import Done, Failed
from e_organon.ports.ocr import OcrWord
from e_organon.providers.adapters.compose.typst import TypstAdapter
from e_organon.providers.adapters.cutout.opencv import OpencvAdapter
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from e_organon.providers.adapters.sign.pyhanko import PyhankoAdapter
from e_organon.services.doc.compose import ComposeDocService
from e_organon.services.doc.ocr import OcrDocService
from e_organon.services.doc.sign import SignDocService
from e_organon.services.doc.signature import SignatureDocService
from e_organon.services.doc.stamp import StampDocService
from e_organon.services.files import AllowedFiles
from e_organon.services.image.cutout import CutoutImageService
from support.ink import ink_png, red_png
from support.ocr import FakeOcr
from support.pdf import blank, form, labelled, rotated
from support.photo import photo

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from pytest_resources import Resources

    from support.pki import Pki
    from support.stamp import Refusal, Stamped


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "form.pdf").write_bytes(form())
    (tmp_path / "three.pdf").write_bytes(blank(3))
    (tmp_path / "labelled.pdf").write_bytes(labelled())
    (tmp_path / "sideways.pdf").write_bytes(rotated(90))
    (tmp_path / "ink.png").write_bytes(ink_png())
    (tmp_path / "firma.jpg").write_bytes(photo()[0])
    return tmp_path


@pytest.fixture
def files(vault: Path) -> AllowedFiles:
    return AllowedFiles((vault,))


@pytest.fixture
def artifacts(vault: Path) -> ArtifactEngine:
    return ArtifactEngine(vault / "outbox")


@pytest.fixture
def pdf() -> PikepdfAdapter:
    return PikepdfAdapter()


@pytest.fixture
def render() -> PdfiumAdapter:
    return PdfiumAdapter()


@pytest.fixture
def stamper(
    pdf: PikepdfAdapter, render: PdfiumAdapter, files: AllowedFiles, artifacts: ArtifactEngine
) -> StampDocService:
    return StampDocService(pdf, render, files, artifacts)


@pytest.fixture
def signer(stamper: StampDocService, files: AllowedFiles, artifacts: ArtifactEngine) -> SignatureDocService:
    return SignatureDocService(CutoutImageService(OpencvAdapter(), files, artifacts, max_pixels=1_000_000), stamper)


@pytest.fixture
async def render_hits(render: PdfiumAdapter) -> list[tuple[float, float, float, float]]:
    """The boxes of `Firma:` on `labelled.pdf`, in page order — where the anchor tests expect the stamp."""
    return [hit.rect for hit in await render.find(labelled(), "firma:")]


@pytest.fixture
def stamped(stamper: StampDocService) -> Stamped:
    """The bytes of the PDF a stamp order makes; the run must end in its answer."""

    async def run(order: StampIn) -> bytes:
        events = [event async for event in stamper.events(order)]
        assert isinstance(events[-1], Done), events[-1]
        assert isinstance(events[-1].result, FileOut)
        return await anyio.Path(events[-1].result.path).read_bytes()

    return run


@pytest.fixture
def refused(stamper: StampDocService) -> Refusal:
    """The `Failed` a stamp order ends in; the run must end in one."""

    async def run(order: StampIn) -> Failed:
        events = [event async for event in stamper.events(order)]
        assert isinstance(events[-1], Failed), events[-1]
        return events[-1]

    return run


@pytest.fixture
def cutter(files: AllowedFiles, artifacts: ArtifactEngine) -> CutoutImageService:
    return CutoutImageService(OpencvAdapter(), files, artifacts, max_pixels=1_000_000)


@pytest.fixture
def golden(vault: Path, resources: Resources) -> Path:
    """The goldens' inputs (`tests/resources/golden`: a signature photo, its mask, a contract) in the vault, with a red 2:1 stamp."""
    for name in ("signature.jpg", "signature.mask.png", "contract.pdf"):
        (vault / name).write_bytes((resources.path / "golden" / name).read_bytes())
    (vault / "red.png").write_bytes(red_png())
    return vault


@pytest.fixture
def ocr_words() -> tuple[OcrWord, ...]:
    """What the fake engine reads on every image: two words on a line, one on the next, boxes in pixels."""
    return (
        OcrWord(text="uno", box=(10, 20, 110, 60)),
        OcrWord(text="dos", box=(130, 22, 230, 62)),
        OcrWord(text="tres", box=(10, 100, 110, 140)),
    )


@pytest.fixture
def fake_ocr(ocr_words: tuple[OcrWord, ...]) -> FakeOcr:
    return FakeOcr(ocr_words)


@pytest.fixture
def reader(fake_ocr: FakeOcr, pdf: PikepdfAdapter, render: PdfiumAdapter, files: AllowedFiles) -> OcrDocService:
    return OcrDocService(fake_ocr, pdf, render, files, max_pixels=5_000_000)


@pytest.fixture
async def sealer(
    pki: Pki,
    stamper: StampDocService,
    signer: SignatureDocService,
    files: AllowedFiles,
    artifacts: ArtifactEngine,
) -> AsyncIterator[SignDocService]:
    async with PyhankoAdapter(p12=pki.p12, password=pki.password, tsa_url=None) as sign:
        yield SignDocService(sign, stamper, signer, files, artifacts)


@pytest.fixture
def templates(vault: Path) -> Path:
    """The deployment's template folder inside the vault, with `hello` — a template that greets `data.name` — and `reads`,
    one that reads `name.txt` beside it."""
    folder = vault / "templates"
    folder.mkdir()
    (folder / "hello.typ").write_bytes(b"#let data = json(bytes(sys.inputs.data))\nHola, #data.name\n")
    (folder / "reads.typ").write_bytes(b'#read("name.txt")')
    (folder / "name.txt").write_text("desde el disco")
    return folder


@pytest.fixture
def composer(files: AllowedFiles, artifacts: ArtifactEngine, templates: Path) -> ComposeDocService:
    """The tool over the real typst adapter, the vault's templates first and the shipped ones after."""
    return ComposeDocService(TypstAdapter(), files, artifacts, folders=(templates, TEMPLATES))
