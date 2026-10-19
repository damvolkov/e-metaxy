"""api.security: bearer enforcement on the REST door — the authority that signs the MCP tokens verifies these.

One token opens both doors: the guard asks the same `Authority` the SDK's gate asks, so a token is valid here
exactly when it is valid on /mcp — signature, expiry, issuer, audience — and the REST door needs `work`. A
refusal answers like the SDK does: 401 with the resource metadata to sign in from, or 403 for a missing scope."""

from enum import StrEnum
from typing import TYPE_CHECKING, Final

from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.openapi.spec import SecurityScheme
from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl

from e_metaxy.core.lifespan.state import AppState
from e_metaxy.models.auth import Scope

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler
    from mcp.server.auth.provider import AccessToken

    from e_metaxy.core.lifespan.services import ServicesState


##### CONTRACT #####
class SecuritySchemeName(StrEnum):
    BEARER = "bearerAuth"


BEARER_SCHEME = SecurityScheme(type="http", scheme="bearer", bearer_format="JWT")
SECURITY: Final[list[dict[str, list[str]]]] = [{SecuritySchemeName.BEARER.value: []}]


##### HELPERS #####
def challenge(services: ServicesState, description: str) -> NotAuthorizedException:
    """A 401 whose `WWW-Authenticate` names the resource metadata, the way the SDK's gate answers on /mcp."""
    metadata = build_resource_metadata_url(AnyHttpUrl(services.policy.resource))
    header = f'Bearer error="invalid_token", error_description="{description}", resource_metadata="{metadata}"'
    return NotAuthorizedException(detail=description, headers={"WWW-Authenticate": header})


async def bearer_access(connection: ASGIConnection) -> AccessToken:
    """The verified access token the request carries, or 401."""
    services: ServicesState = AppState.of(connection.app).system.services
    match connection.headers.get("authorization", "").split():
        case ["Bearer", token]:
            match await services.authority.load_access_token(token):
                case None:
                    raise challenge(services, "Invalid or expired token")
                case access:
                    return access
        case _:
            raise challenge(services, "Authentication required")


async def auth_guard(connection: ASGIConnection, _handler: BaseRouteHandler) -> None:
    """Litestar calls guards with (connection, handler): a valid token carrying `work`, or the request stops."""
    access = await bearer_access(connection)
    match Scope.WORK.value in access.scopes:
        case False:
            raise PermissionDeniedException(detail=f"this token lacks the {Scope.WORK.value!r} scope")
        case _:
            pass
