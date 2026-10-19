"""core.lifespan.adapters: open every external edge on one exit stack.

`AdaptersState` names each edge by the port its consumers ask of it — the graph carries contracts, not
classes. Every adapter is a singleton built here; iterating the section yields the edges in the order they
open, and the stack closes them in reverse. OpenHuman is called back only when its core token is set."""

from collections.abc import AsyncGenerator, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import cast

from litestar import Litestar

from e_metaxy.adapters.anytomd import AnytomdAdapter
from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.adapters.openhuman import OpenHumanAdapter
from e_metaxy.adapters.ports import DocumentPort, MdConvertPort, StorePort
from e_metaxy.adapters.sqlite import SQLiteAdapter
from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.logger import logger
from e_metaxy.core.settings import settings as st
from e_metaxy.core.settings.db import DbSettings
from e_metaxy.core.settings.metaxy import MetaxySettings
from e_metaxy.logic.ports import CoderPort, NotifierPort


##### SECTION #####
@dataclass(frozen=True, slots=True)
class AdaptersState:
    """The typed adapters section: `store` is the ledger, `coder` the engineer harness, `md`/`doc` the
    converters' engines, `callers` the polymath harnesses a finished task calls back."""

    store: StorePort
    coder: CoderPort
    md: MdConvertPort
    doc: DocumentPort
    callers: Mapping[str, NotifierPort]

    def __iter__(self) -> Iterator[AbstractAsyncContextManager[object]]:
        ### every port here is served by an adapter that is its own async context manager.
        edges = (self.store, self.coder, self.md, self.doc, *self.callers.values())
        return iter(cast("tuple[AbstractAsyncContextManager[object], ...]", edges))


def callers(conf: MetaxySettings) -> Mapping[str, NotifierPort]:
    """The callers the bridge can call back — OpenHuman only when its core token is configured."""
    match conf.openhuman_token:
        case None:
            return {}
        case token:
            notifier = OpenHumanAdapter(conf.openhuman_url, token.get_secret_value(), timeout=conf.openhuman_timeout)
            return {notifier.name: notifier}


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Open every external edge on the exit stack, then mount the typed section under `system.adapters`."""
    system, conf = AppState.of(app).system, st.metaxy
    edges = AdaptersState(
        store=SQLiteAdapter(DbSettings(db_path=conf.ledger.expanduser())),
        coder=ClaudeCoder(conf.claude),
        md=AnytomdAdapter(),
        doc=DoclingAdapter(),
        callers=callers(conf),
    )
    async with AsyncExitStack() as stack:
        _ = [await stack.enter_async_context(edge) for edge in edges]
        system.adapters = edges
        logger.info("adapters ready", callers=sorted(edges.callers), step="START")
        yield
    logger.info("adapters closed", step="STOP")
