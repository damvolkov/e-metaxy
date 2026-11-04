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


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Open every provider on the exit stack, then mount the typed section under `system.providers`."""
    system = AppState.of(app).system
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        store = await enter(SqliteDriver())
        redis = await enter(RedisDriver())
        http = await enter(WreqDriver())
        database = await enter(PsqlpyDriver())
        auth = await enter(PostgresAuthDriver(database))
        markdown = await enter(AnytomdAdapter())
        pages = await enter(LiteparseAdapter())
        pdf = await enter(PikepdfAdapter())
        render = await enter(PdfiumAdapter())
        coder = await enter(ClaudeDriver(st.services.TEKTON_CLAUDE)) if st.services.TEKTON_PROFILES else None
        docling = await enter(DoclingDriver(http)) if st.providers.drivers.documents.docling.url else None
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
