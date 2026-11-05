"""e-organon entrypoint: assembly by explicit registration only — importing this module does nothing.

`create_app` is the composition root and the factory granian calls per worker. One Litestar app serves both doors:
the REST routes, and the MCP endpoint whose tools are routes too (`mcp/registry`), each reached in process by the MCP
engine (`infra/mcp`) and answering it alone. Both sit behind the same middleware stack — the caller resolved once, from
the key — and the same guard, at the access each route and tool declares. Routers and websockets enter through
`register` calls — the include_router shape; middleware, the lifespan chain and CORS enter through the constructor, and
the order of `lifespan=[...]` is the startup order: infra first (every later concern may depend on the loaded
singletons), then the providers, the engines over their ports and the services, the jobs (the dispatch entered once
its kinds are registered), the MCP server, sealed last. Dependency
chains are wired by each endpoint, never here. The settings are read once, at import (`infra.settings`); this root
reads `st` and hands each door its values.
"""

from importlib.metadata import version
from typing import Final, cast

from litestar import Litestar
from litestar.openapi.spec import Components
from litestar.router import Router
from litestar.types import Middleware

from e_organon.api import docs
from e_organon.api.lifespan import db, engines, jobs, mcp, providers, sealed, services
from e_organon.api.lifespan.infra import lifespan as infra_lifespan
from e_organon.api.middlewares import MIDDLEWARES, cors_config
from e_organon.api.router import auth, doc, health, image, organon, tekton
from e_organon.api.router import jobs as jobs_router
from e_organon.api.security import BEARER_SCHEME, SecuritySchemeName
from e_organon.api.state import AppState
from e_organon.infra.auth.guard import OPT, guard
from e_organon.infra.auth.models import Access
from e_organon.infra.logger import ELogger
from e_organon.infra.mcp.guard import internal
from e_organon.infra.settings import settings as st
from e_organon.infra.state import State
from e_organon.mcp import mount
from e_organon.mcp import registry as tools

### the API's routers, each route declaring its access (`opt=OPT[...]`); the bridge's join them only where it is on.
GUARDED: Final = (health.ROUTES, auth.ROUTES, doc.ROUTES, image.ROUTES, jobs_router.ROUTES, organon.ROUTES)


def create_app() -> Litestar:
    """Composition root: granian calls this per worker. Nothing here builds — the lifespans write the system graph."""
    ### the logger takes APP_ENV from the root, before any line is logged: JSON in prod, flat text elsewhere.
    ELogger.setup(env=st.APP_ENV)
    ##### APP #####
    app = Litestar(
        route_handlers=[],
        ### Litestar's own state class, typed: one entry, the infra graph the lifespans write and seal.
        state=AppState({"system": State()}),
        lifespan=[
            infra_lifespan,
            db.lifespan,
            providers.lifespan,
            engines.lifespan,
            services.lifespan,
            jobs.lifespan,
            mcp.lifespan,
            sealed.lifespan,
        ],
        ### the declared union of middlewares crosses into litestar's looser `Middleware` alias here;
        ### asgi_correlation_id types its scope narrower than the protocol — wiring is exact, upstream typing is not.
        middleware=cast("list[Middleware]", list(MIDDLEWARES)),
        cors_config=cors_config(origins=st.ALLOW_ORIGINS, methods=st.ALLOW_METHODS),
        ### pyproject is the version source of truth: uv-dynamic-versioning stamps it, dev reads 0.0.0.
        ### where the docs live, their aliases and renderers: DOCS_* settings, translated by api.docs.
        openapi_config=docs.openapi_config(
            title="e-organon",
            version=version("e-organon"),
            path=st.DOCS_PATH,
            renderers=st.DOCS_RENDERERS,
            components=Components(security_schemes={SecuritySchemeName.BEARER.value: BEARER_SCHEME}),
        ),
    )

    ##### ROUTERS #####
    ### every route passes the one guard, at the access it declares: each API route its own, the docs public (never
    ### authenticated).
    bridge = st.TEKTON_PROFILES is not None
    guarded = (*GUARDED, *([tekton.ROUTES] if bridge else []), *([doc.OCR] if st.OCR_ENABLED else []))
    _ = [app.register(Router(path="/", route_handlers=list(routes), guards=[guard])) for routes in guarded]
    app.register(
        Router(
            path="/",
            route_handlers=list(docs.routes(path=st.DOCS_PATH, aliases=st.DOCS_ALIASES)),
            opt=OPT[Access.PUBLIC],
            guards=[guard],
        )
    )
    ### the MCP door: the tools, routes the engine alone may reach, each at the access its tool declares; the endpoint, any
    ### caller's — the token middleware has resolved who, each tool admits it at its own.
    app.register(
        Router(path="/", route_handlers=list(tools.routes(bridge=bridge, ocr=st.OCR_ENABLED)), guards=[internal, guard])
    )
    app.register(
        Router(path="/", route_handlers=list(mount.routes(path=st.MCP_PATH)), opt=OPT[Access.ANONYMOUS], guards=[guard])
    )
    return app
