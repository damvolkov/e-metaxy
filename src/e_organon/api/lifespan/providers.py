"""api.lifespan.providers: open every provider on one exit stack.

The concern owns its subtree as a typed section: `ProvidersState` names each provider by the port the
consumers (api.deps, routers, engines) may ask of it, so the graph carries contracts, not classes. Each
provider is a singleton built here, enters the shared `AsyncExitStack` in field order, and they close
in reverse when the stack unwinds. Every provider is one line per block — its import, its field, its
construction — so an exported project that drops a driver loses exactly those lines. Their health is the
engines' concern (`api/lifespan/engines`)."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, fields

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.ports.auth import AuthPort
from e_organon.ports.coder import CoderPort
from e_organon.ports.database import DatabasePort
from e_organon.ports.documents import DocumentPort
from e_organon.ports.http import HTTPPort
from e_organon.ports.markdown import MarkdownPort
from e_organon.ports.pages import PagesPort
from e_organon.ports.pdf import PdfPort
from e_organon.ports.provider import Provider
from e_organon.ports.render import RenderPort
from e_organon.ports.store import StorePort
from e_organon.providers.adapters.markdown.anytomd import AnytomdAdapter
from e_organon.providers.adapters.pages.liteparse import LiteparseAdapter
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from e_organon.providers.drivers.auth.postgres import PostgresAuthDriver
from e_organon.providers.drivers.coder.claude import ClaudeDriver
from e_organon.providers.drivers.database.psqlpy import PsqlpyDriver
from e_organon.providers.drivers.documents.docling import DoclingDriver
from e_organon.providers.drivers.http.wreq import WreqDriver
from e_organon.providers.drivers.store.redis import RedisDriver
from e_organon.providers.drivers.store.sqlite import SqliteDriver

### the roles a deployment may leave empty: each stays out of `named` (and the health survey) until its setting is set.
OPTIONAL: frozenset[str] = frozenset({"docling"})


##### SECTION #####
@dataclass(frozen=True, slots=True)
class ProvidersState:
    """The typed providers section: fields named by role, typed by the port the role speaks.

    `store` is the KV edge the app's records live on; `auth` is where accounts and keys live, over `database`, the
    service's one SQL pool; `coder` is the engineer harness the tekton tools drive; any further field is an optional
    provider the export may drop. The providers are
    singletons — factory machinery comes later."""

    store: StorePort
    redis: StorePort
    http: HTTPPort
    database: DatabasePort
    auth: AuthPort
    markdown: MarkdownPort
    pages: PagesPort
    pdf: PdfPort
    render: RenderPort
    ### the coder opens only with the bridge on (TEKTON_PROFILES): the public image carries no Claude CLI.
    coder: CoderPort | None
    ### docling-serve is optional: present only when DOCLING_URL is set — the doc tools read without it.
    docling: DocumentPort | None

    @property
    def named(self) -> Mapping[str, Provider]:
        """Every provider by its role, in field order — what the health engine surveys."""
        return {each.name: found for each in fields(self) if (found := getattr(self, each.name)) is not None}


##### FACTORIES #####
def anytomd() -> AnytomdAdapter:
    """The any-format reader, MD_*."""
    return AnytomdAdapter(
        vision_base_url=st.MD_VISION_BASE_URL,
        vision_api_key=st.MD_VISION_API_KEY,
        vision_model=st.MD_VISION_MODEL,
        vision_prompt=st.MD_VISION_PROMPT,
        image_describe=st.MD_IMAGE_DESCRIBE,
        max_input_bytes=st.MD_MAX_INPUT_BYTES,
        pdf_workers=st.MD_PDF_WORKERS,
        pdf_ocr=st.MD_PDF_OCR,
        pdf_language=st.MD_PDF_LANGUAGE,
        strict=st.MD_STRICT,
        extract_comments=st.MD_EXTRACT_COMMENTS,
    )


def liteparse() -> LiteparseAdapter:
    """The fast page reader, DOC_WORKERS / DOC_OCR / DOC_OCR_LANGUAGE; its OCR models in doc/'s subtree of ORGANON_DATA
    unless DOC_TESSDATA names another place."""
    tessdata = st.DOC_TESSDATA or st.ORGANON_DATA / "doc" / "models" / "tessdata"
    return LiteparseAdapter(
        workers=st.DOC_WORKERS, ocr=st.DOC_OCR, tessdata=tessdata.expanduser(), ocr_language=st.DOC_OCR_LANGUAGE
    )


def docling_driver(http: HTTPPort) -> DoclingDriver:
    """The deep reader over docling-serve, DOCLING_*."""
    return DoclingDriver(
        http,
        url=st.DOCLING_URL,
        timeout=st.DOCLING_TIMEOUT,
        deadline=st.DOCLING_DEADLINE,
        poll=st.DOCLING_POLL,
        page_timeout=st.DOCLING_PAGE_TIMEOUT,
        formats=st.DOCLING_FORMATS,
        images=st.DOCLING_IMAGES,
        images_scale=st.DOCLING_IMAGES_SCALE,
        tables=st.DOCLING_TABLES,
        ocr=st.DOCLING_OCR,
        force_ocr=st.DOCLING_FORCE_OCR,
        ocr_engine=st.DOCLING_OCR_ENGINE,
        ocr_lang=st.DOCLING_OCR_LANG,
        backend=st.DOCLING_BACKEND,
        formulas=st.DOCLING_FORMULAS,
        pictures=st.DOCLING_PICTURES,
        charts=st.DOCLING_CHARTS,
        code=st.DOCLING_CODE,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Open every provider on the exit stack, then mount the typed section under `system.providers`."""
    system = AppState.of(app).system
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        store = await enter(SqliteDriver(path=st.DB_PATH, timeout=st.DB_TIMEOUT))
        redis = await enter(RedisDriver(url=st.REDIS_URL, pool=st.REDIS_POOL, timeout=st.REDIS_TIMEOUT))
        http = await enter(
            WreqDriver(base_url=st.HTTP_BASE_URL, timeout=st.HTTP_TIMEOUT, agent=st.HTTP_AGENT, headers=st.HTTP_HEADERS)
        )
        database = await enter(PsqlpyDriver(dsn=st.POSTGRES_DSN, pool=st.POSTGRES_POOL, timeout=st.POSTGRES_TIMEOUT))
        auth = await enter(PostgresAuthDriver(database))
        markdown = await enter(anytomd())
        pages = await enter(liteparse())
        pdf = await enter(PikepdfAdapter())
        render = await enter(PdfiumAdapter())
        coder = await enter(ClaudeDriver(st.TEKTON_CLAUDE)) if st.TEKTON_PROFILES else None
        docling = await enter(docling_driver(http)) if st.DOCLING_URL else None
        providers = ProvidersState(
            store=store,
            redis=redis,
            http=http,
            database=database,
            auth=auth,
            markdown=markdown,
            pages=pages,
            pdf=pdf,
            render=render,
            coder=coder,
            docling=docling,
        )
        system.providers = providers
        logger.info("providers ready", providers=sorted(providers.named), step="START")
        yield
    logger.info("providers closed", step="STOP")
