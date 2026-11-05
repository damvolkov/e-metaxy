"""api.lifespan.jobs: the dispatch entered, once every kind it will run is registered.

Registration on the dispatch engine is open until it is entered (`engines/dispatch`): the engines concern builds it, and
this one — after the services whose tools become kinds exist — enters it for the app's life. The durable queue it
prefers is PgQueuer on the queue's database; one that cannot be reached is a warning and memory alone, never a crash.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Enter the dispatch engine for the app's life; it closes, cancelling what runs, when the app stops."""
    dispatch = AppState.of(app).system.engines.dispatch
    async with dispatch:
        logger.info("dispatch ready", engine=dispatch.engine, kinds=len(dispatch.kinds), step="START")
        yield
