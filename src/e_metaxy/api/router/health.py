"""api.router.health: liveness — no graph access, it answers even while an engine is down."""

from litestar import get
from litestar.handlers import HTTPRouteHandler


async def health() -> dict[str, str]:
    """Liveness probe: the app is up and routing."""
    return {"status": "ok"}


ROUTES: tuple[HTTPRouteHandler, ...] = (get("/health", name="health", include_in_schema=False)(health),)
