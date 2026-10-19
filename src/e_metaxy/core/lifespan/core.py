"""core.lifespan.core: the one-time load of the shared core singletons, mirrored as a typed graph section.

`settings` and `logger` are `LazyProxy`s: nothing loads at import, the first attribute access pays for the
load exactly once per process. This lifespan *is* that first access — granian builds the app in its worker,
so the logger is configured where the app runs — and it routes the third-party stdlib logs (the MCP SDK's
rich handler) into structlog before any MCP server exists. The loaded pair lands under `system.core`."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog
from litestar import Litestar
from structlog.typing import BindableLogger

from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.logger import logger
from e_metaxy.core.proxy import LazyProxy
from e_metaxy.core.settings import Settings
from e_metaxy.core.settings import settings as st


##### SECTION #####
@dataclass(frozen=True, slots=True)
class CoreState:
    """The typed core section: exactly the two singletons every other concern may depend on."""

    settings: Settings
    logger: LazyProxy[BindableLogger]


class StdlibHandler(logging.Handler):
    """A stdlib record as a structlog event: what the MCP SDK logs through rich enters the house renderer."""

    def emit(self, record: logging.LogRecord) -> None:
        structlog.get_logger(record.name).log(
            record.levelno, record.getMessage(), exc_info=record.exc_info, stack_info=record.stack_info
        )


def quiet() -> None:
    """Route the stdlib root to structlog once: the SDK's `basicConfig` then finds it handled and adds no RichHandler."""
    match any(isinstance(handler, StdlibHandler) for handler in logging.root.handlers):
        case False:
            logging.root.addHandler(StdlibHandler())
        case _:
            pass
    logging.root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Force the lazy core load once, route the stdlib logs, then mirror the pair into `system.core`."""
    system = AppState.of(app).system
    ### first attribute access builds and caches each singleton: app_env loads settings, this line configures structlog.
    logger.info("core ready", env=st.app.app_env, step="START")
    quiet()
    system.core = CoreState(settings=st, logger=logger)
    yield
