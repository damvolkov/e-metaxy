import logging

from e_metaxy.core.lifespan.core import CoreState, StdlibHandler, quiet
from e_metaxy.core.logger import logger
from e_metaxy.core.settings import settings as st


async def test_core_section_holds_the_loaded_singletons(app) -> None:
    core = app.state.system.core
    assert isinstance(core, CoreState)
    assert (core.settings is st, core.logger is logger) == (True, True)


async def test_core_routes_stdlib_once(app) -> None:
    routed = [handler for handler in logging.root.handlers if isinstance(handler, StdlibHandler)]
    assert len(routed) == 1
    assert not any(type(handler).__module__.startswith("rich") for handler in logging.root.handlers)
    logging.getLogger("mcp.test").warning("routed without raising")


def test_core_quiet_is_idempotent() -> None:
    quiet()
    quiet()
    assert len([handler for handler in logging.root.handlers if isinstance(handler, StdlibHandler)]) == 1
