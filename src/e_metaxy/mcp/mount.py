"""e_metaxy.mcp.mount: the MCP server as Litestar mounts — the SDK serves exactly the paths it owns.

The SDK's app answers /mcp, the OAuth endpoints and their metadata; it is built by the mcp lifespan and read
off the sealed graph on every call, so the routes exist before the server does. Each prefix is named: a
catch-all mount would shadow litestar's own path-parameter routes. Litestar strips the mount prefix from the
path; the SDK routes on the whole one, so the forwarder hands it back."""

from typing import Final
from urllib.parse import unquote

from litestar import Litestar, asgi
from litestar.handlers import ASGIRouteHandler
from litestar.types import Receive, Scope, Send

from e_metaxy.core.lifespan.state import AppState


async def forward(scope: Scope, receive: Receive, send: Send) -> None:
    """The request, its full path restored, to the SDK's Streamable HTTP app."""
    whole = {**scope, "path": unquote(scope["raw_path"].decode()), "root_path": ""}
    await AppState.of(Litestar.from_scope(scope)).system.mcp.app(whole, receive, send)


### the transport, the authorization server (RFC 8414 metadata, RFC 7591 registration, the OAuth 2.1 endpoints,
### RFC 7009 revocation) and the protected-resource metadata (RFC 9728) — the SDK's whole surface.
PATHS: Final = ("/mcp", "/.well-known", "/authorize", "/token", "/register", "/revoke")

##### ROUTES #####
ROUTES: tuple[ASGIRouteHandler, ...] = (asgi(list(PATHS), name="mcp", is_mount=True, copy_scope=True)(forward),)
