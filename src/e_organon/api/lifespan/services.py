"""api.lifespan.services: assemble what travels with the app — crypto, and the canonical tools by section.

Crypto is written into the system graph — the user records' password hashing. Each tool is built over the providers'
ports and hangs at `services.<section>.<tool>`, the attribute chain the routes read (`graph.services.doc.convert`).
They are pure in-process objects over providers the providers concern closes, so this concern owns no resource.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.ops.crypto import Crypto
from e_organon.processors.doc import DocProcessor
from e_organon.services.doc.convert import ConvertDocService
from e_organon.services.doc.fill import FillDocService
from e_organon.services.doc.inspect import InspectDocService
from e_organon.services.doc.merge import MergeDocService
from e_organon.services.doc.render import RenderDocService
from e_organon.services.doc.split import SplitDocService
from e_organon.services.files import AllowedFiles


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Assemble what travels with the app: crypto, then each section's tools over the open providers."""
    system = AppState.of(app).system
    system.crypto = Crypto(st.crypto)
    found, files = system.providers, AllowedFiles(st.services.ORGANON_ROOTS)
    artifacts = system.engines.artifact
    doc = system.services.doc
    doc.convert = ConvertDocService(DocProcessor(found.markdown, found.pages, found.docling), files)
    doc.inspect = InspectDocService(found.pdf, files)
    doc.merge = MergeDocService(found.pdf, files, artifacts)
    doc.split = SplitDocService(found.pdf, files, artifacts)
    doc.fill = FillDocService(found.pdf, files, artifacts)
    doc.render = RenderDocService(found.render, files, artifacts)
    logger.info("services ready", step="START")
    yield
