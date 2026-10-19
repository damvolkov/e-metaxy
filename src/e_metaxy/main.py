"""e_metaxy.main: assembly by explicit registration only — importing this module does nothing.

`create_app` is the composition root and the factory granian calls per worker. One Litestar app serves both
doors: the REST routes (consent, `/ops`) it routes itself, and the MCP server — /mcp, the OAuth endpoints and
their metadata — through mounts on exactly the paths the SDK owns. Both sit behind
the same middleware stack and read the same sealed graph. The order of `lifespan=[...]` is the startup order:
core first, then the edges, the services built over them, the MCP server built over the services, sealed last.
Nothing here builds — the lifespans write the system graph."""

from importlib.metadata import version
from typing import cast

from litestar import Litestar
from litestar.openapi.spec import Components
from litestar.router import Router
from litestar.types import Middleware

from e_metaxy.api import docs
from e_metaxy.api.router import consent, converters, health
from e_metaxy.api.security import BEARER_SCHEME, SecuritySchemeName
from e_metaxy.core.lifespan import adapters, mcp, sealed, services
from e_metaxy.core.lifespan.core import lifespan as core_lifespan
from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.middlewares import MIDDLEWARES, cors_config
from e_metaxy.core.state import State
from e_metaxy.mcp import mount


def create_app() -> Litestar:
    """Composition root: granian calls this per worker. Nothing here builds — the lifespans write the system graph."""
    ##### APP #####
    app = Litestar(
        route_handlers=[],
        ### Litestar's own state class, typed: one entry, the core graph the lifespans write and seal.
        state=AppState({"system": State()}),
        lifespan=[core_lifespan, adapters.lifespan, services.lifespan, mcp.lifespan, sealed.lifespan],
        ### the declared union of middlewares crosses into litestar's looser `Middleware` alias here.
        middleware=cast("list[Middleware]", list(MIDDLEWARES)),
        ### structlog is the only logger: the core lifespan routes stdlib into it, litestar's own config would echo.
        logging_config=None,
        cors_config=cors_config(),
        openapi_config=docs.openapi_config(
            title="e-metaxy",
            version=version("e-metaxy"),
            components=Components(security_schemes={SecuritySchemeName.BEARER.value: BEARER_SCHEME}),
        ),
    )

    ##### ROUTERS #####
    app.register(Router(path="/", route_handlers=list(health.ROUTES)))
    app.register(Router(path="/", route_handlers=list(consent.ROUTES)))
    app.register(Router(path=converters.PREFIX, route_handlers=list(converters.ROUTES)))
    app.register(Router(path="/", route_handlers=list(docs.routes())))
    app.register(Router(path="/", route_handlers=list(mount.ROUTES)))
    return app
