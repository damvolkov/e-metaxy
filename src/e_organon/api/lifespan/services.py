"""api.lifespan.services: assemble what travels with the app — crypto, and the canonical tools by section.

Crypto is written into the system graph — the user records' password hashing. Each tool is built over the providers'
ports and hangs at `services.<section>.<tool>`, the attribute chain the routes read (`graph.services.doc.convert`).
They are pure in-process objects over providers the providers concern closes, so this concern owns no resource.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.ops.crypto import Crypto, CryptoKeys
from e_organon.ops.projects import NamedProjects
from e_organon.ports.documents import DocumentPort
from e_organon.ports.markdown import MarkdownPort
from e_organon.ports.pages import PagesPort
from e_organon.processors.doc import DocProcessor
from e_organon.services.doc.compose import ComposeDocService
from e_organon.services.doc.convert import ConvertDocService
from e_organon.services.doc.fill import FillDocService
from e_organon.services.doc.inspect import InspectDocService
from e_organon.services.doc.merge import MergeDocService
from e_organon.services.doc.ocr import OcrDocService
from e_organon.services.doc.render import RenderDocService
from e_organon.services.doc.sign import SignDocService
from e_organon.services.doc.signature import SignatureDocService
from e_organon.services.doc.split import SplitDocService
from e_organon.services.doc.stamp import StampDocService
from e_organon.services.files import AllowedFiles
from e_organon.services.image.barcode import BarcodeImageService
from e_organon.services.image.budget import BudgetImage
from e_organon.services.image.convert import ConvertImageService
from e_organon.services.image.cutout import CutoutImageService
from e_organon.services.tekton.cancel import CancelTektonService
from e_organon.services.tekton.catalog import CatalogTektonService
from e_organon.services.tekton.eng import EngTektonService
from e_organon.services.tekton.find import FindTektonService
from e_organon.services.tekton.peers import PeersTektonService
from e_organon.services.tekton.read import ReadTektonService
from e_organon.services.tekton.send import SendTektonService
from e_organon.services.tekton.start import StartTektonService
from e_organon.services.tekton.status import StatusTektonService
from e_organon.services.tekton.tasks import TasksTektonService
from e_organon.services.tekton.update import UpdateTektonService

### the templates shipped with the package (`doc/compose` names them after the deployment's own folder).
TEMPLATES: Final[Path] = Path(__file__).resolve().parents[2] / "templates"


##### FACTORIES #####
def reader(markdown: MarkdownPort, pages: PagesPort, docling: DocumentPort | None) -> DocProcessor:
    """The document reader over its three providers, DOC_*."""
    return DocProcessor(
        markdown,
        pages,
        docling,
        concurrency=st.DOC_CONCURRENCY,
        span=st.DOC_SPAN,
        gap=st.DOC_GAP,
        mode=st.DOC_MODE,
        route=st.DOC_ROUTE,
        tables=st.DOC_TABLES,
        max_input_bytes=st.DOC_MAX_INPUT_BYTES,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Assemble what travels with the app: crypto, then each section's tools over the open providers."""
    system = AppState.of(app).system
    system.crypto = Crypto(
        CryptoKeys(
            secret=st.CRYPTO__SECRET,
            alg=st.CRYPTO__ALG,
            enc=st.CRYPTO__ENC,
            private_key=st.CRYPTO__PRIVATE_KEY.get_secret_value(),
            hasher=st.CRYPTO__HASHER,
            bcrypt_rounds=st.CRYPTO__BCRYPT_ROUNDS,
        )
    )
    found, files = system.providers, AllowedFiles(st.ORGANON_ROOTS)
    artifacts = system.engines.artifact
    doc = system.services.doc
    doc.convert = ConvertDocService(reader(found.markdown, found.pages, found.docling), files)
    doc.inspect = InspectDocService(found.pdf, files)
    doc.merge = MergeDocService(found.pdf, files, artifacts)
    doc.split = SplitDocService(found.pdf, files, artifacts)
    doc.fill = FillDocService(found.pdf, files, artifacts)
    doc.render = RenderDocService(found.render, files, artifacts)
    doc.stamp = StampDocService(found.pdf, found.render, files, artifacts)
    doc.compose = ComposeDocService(
        found.compose,
        found.pdf,
        files,
        artifacts,
        folders=(st.ORGANON_DATA / "doc" / "templates", TEMPLATES),
        max_pages=st.ORGANON_MAX_PAGES,
    )
    image = system.services.image
    image.cutout = CutoutImageService(found.cutout, files, artifacts, max_pixels=st.ORGANON_MAX_PIXELS)
    budget = BudgetImage(found.raster.size, max_pixels=st.ORGANON_MAX_PIXELS)
    image.convert = ConvertImageService(found.raster, files, artifacts, budget)
    image.barcode = BarcodeImageService(found.barcode, files, artifacts, budget)
    doc.signature = SignatureDocService(image.cutout, doc.stamp)
    ### `doc/ocr` exists only with its engine open (OCR_ENABLED).
    match found.ocr:
        case None:
            pass
        case ocr:
            doc.ocr = OcrDocService(ocr, found.pdf, found.render, files, max_pixels=st.ORGANON_MAX_PIXELS)
    ### `doc/sign` exists only with its key configured (SIGN_P12).
    match found.sign:
        case None:
            pass
        case sign:
            doc.sign = SignDocService(sign, doc.stamp, doc.signature, files, artifacts)
    ### the tekton tools exist only with the bridge on.
    match system.engines.bridge:
        case None:
            pass
        case bridge:
            tekton = system.services.tekton
            tekton.eng = EngTektonService(bridge, NamedProjects(st.TEKTON_WORKSPACES))
            tekton.start = StartTektonService(bridge)
            tekton.status = StatusTektonService(bridge)
            tekton.tasks = TasksTektonService(bridge)
            tekton.cancel = CancelTektonService(bridge)
            tekton.catalog = CatalogTektonService(bridge)
            tekton.find = FindTektonService(bridge)
            tekton.read = ReadTektonService(bridge)
            ### `update` is a method of `State` (a mapping): its node is written, and read, by key.
            tekton["update"] = UpdateTektonService(bridge)
            tekton.peers = PeersTektonService(bridge)
            tekton.send = SendTektonService(bridge)
    logger.info("services ready", step="START")
    yield
