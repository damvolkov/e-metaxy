"""api.lifespan.services: assemble what travels with the app — crypto, and the canonical tools by section.

Crypto is written into the system graph — the user records' password hashing. Each tool is built over the providers'
ports and hangs at `services.<section>.<tool>`, the attribute chain the routes read (`graph.services.doc.convert`).
They are pure in-process objects over providers the providers concern closes, so this concern owns no resource.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.services.doc.convert import ConvertDocService
from e_organon.services.files import AllowedFiles
from infra.logger import logger
from infra.settings import settings as st
from ops.crypto import Crypto
from processors.doc import DocProcessor


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Assemble what travels with the app: crypto, then each section's tools over the open providers."""
    system = AppState.of(app).system
    system.crypto = Crypto(st.crypto)
    found, files = system.providers, AllowedFiles()
    system.services.doc.convert = ConvertDocService(DocProcessor(found.markdown, found.pages, found.docling), files)
    logger.info("services ready", step="START")
    yield
