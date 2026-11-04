"""core.lifespan.adapters: open every external edge on one exit stack.

`AdaptersState` names each edge by the port its consumers ask of it — the graph carries contracts, not
classes. Every adapter is a singleton built here; iterating the section yields the edges in the order they
open, and the stack closes them in reverse."""

from collections.abc import AsyncGenerator, Iterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import cast

from litestar import Litestar

from e_metaxy.adapters.anytomd import AnytomdAdapter
from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.adapters.ports import DocumentPort, MdConvertPort, StorePort
from e_metaxy.adapters.sqlite import SQLiteAdapter
from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.logger import logger
from e_metaxy.core.settings import settings as st
from e_metaxy.core.settings.db import DbSettings
from e_metaxy.logic.ports import CoderPort


##### SECTION #####
@dataclass(frozen=True, slots=True)
class AdaptersState:
    """The typed adapters section: `store` is the ledger, `coder` the engineer harness, `md`/`doc` the
    converters' engines."""

    store: StorePort
    coder: CoderPort
    md: MdConvertPort
    doc: DocumentPort

    def __iter__(self) -> Iterator[AbstractAsyncContextManager[object]]:
        ### every port here is served by an adapter that is its own async context manager.
        edges = (self.store, self.coder, self.md, self.doc)
        return iter(cast("tuple[AbstractAsyncContextManager[object], ...]", edges))


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Open every external edge on the exit stack, then mount the typed section under `system.adapters`."""
    system, conf = AppState.of(app).system, st.metaxy
    edges = AdaptersState(
        store=SQLiteAdapter(DbSettings(db_path=conf.ledger.expanduser())),
        coder=ClaudeCoder(conf.claude),
        md=AnytomdAdapter(),
        doc=DoclingAdapter(),
    )
    async with AsyncExitStack() as stack:
        _ = [await stack.enter_async_context(edge) for edge in edges]
        system.adapters = edges
        logger.info("adapters ready", step="START")
        yield
    logger.info("adapters closed", step="STOP")
