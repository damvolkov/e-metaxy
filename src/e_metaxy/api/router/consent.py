"""api.router.consent: the one page a person sees — the owner approves or denies a client's authorization.

GET shows the parked request (who asks, where the answer goes back, what it may do) and a passphrase field;
POST decides. Approval or denial ends in a redirect to the client; a wrong passphrase shows the page again
until the attempts run out. The request id travels in the form: it is unguessable, single use and short-lived,
which is what a CSRF token would be. Every value on the page is escaped; the page carries no script."""

import html
from enum import StrEnum, auto
from typing import Annotated, Final
from urllib.parse import urlparse

import msgspec
from litestar import MediaType, Response, get, post
from litestar.di import NamedDependency, Provide
from litestar.enums import RequestEncodingType
from litestar.handlers import HTTPRouteHandler
from litestar.params import Body, QueryParameter
from litestar.response import Redirect
from litestar.status_codes import HTTP_302_FOUND, HTTP_410_GONE

from e_metaxy.api.deps import DepKey, authority, graph
from e_metaxy.logic.authority import CONSENT_PATH, Authority
from e_metaxy.models.auth import Consent
from e_metaxy.models.error import UnknownConsentError

SCOPES: Final = {
    "work": "start, watch and cancel work in Claude Code",
    "sessions": "find, read and rename Claude Code sessions",
    "live": "list and message your open Claude Code sessions",
}
PAGE: Final = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>e-metaxy · authorize</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;color:#222}}
code{{background:#f2f2f2;padding:0 .3rem}}li{{margin:.2rem 0}}.e{{color:#a00}}
button{{font:inherit;padding:.4rem 1rem;margin-right:.5rem}}input{{font:inherit;width:100%;padding:.4rem}}
</style></head><body><h1>Authorize a client</h1>
<p><b>{client}</b> asks to use e-metaxy. The answer goes back to <code>{host}</code>.</p>
<p>It may:</p><ul>{scopes}</ul>{error}
<form method="post" action="{action}"><input type="hidden" name="request" value="{request}">
<p><label>Passphrase<br><input type="password" name="passphrase" autocomplete="current-password" autofocus></label></p>
<button name="decision" value="approve">Approve</button><button name="decision" value="deny">Deny</button>
</form></body></html>"""
GONE: Final = "<!doctype html><title>e-metaxy</title><p>{message}</p>"
HEADERS: Final = {"Cache-Control": "no-store", "X-Frame-Options": "DENY"}
WRONG: Final = "That passphrase is not the owner's."


##### CONTRACT #####
class Decision(StrEnum):
    APPROVE = auto()
    DENY = auto()


class ConsentForm(msgspec.Struct, frozen=True, kw_only=True):
    """What the page posts back: the parked request, the owner's choice and, to approve, the passphrase."""

    request: str = ""
    decision: str = ""
    passphrase: str = ""


##### HELPERS #####
def page(consent: Consent, error: str = "") -> Response[str]:
    """The consent page for a parked request, every value escaped."""
    escape = html.escape
    return Response(
        PAGE.format(
            client=escape(consent.client_name),
            host=escape(urlparse(consent.redirect_uri).netloc or consent.redirect_uri),
            scopes="".join(f"<li>{escape(SCOPES.get(scope, scope))}</li>" for scope in consent.scopes),
            error=f'<p class="e">{escape(error)}</p>' if error else "",
            action=escape(CONSENT_PATH),
            request=escape(consent.id),
        ),
        media_type=MediaType.HTML,
        headers=HEADERS,
    )


def gone(error: UnknownConsentError) -> Response[str]:
    """An unknown, used or expired request: 410, nothing to decide."""
    return Response(
        GONE.format(message=html.escape(error.message)), media_type=MediaType.HTML, status_code=HTTP_410_GONE
    )


async def approve(authority: Authority, form: ConsentForm) -> Response[str] | Redirect:
    """The client's redirect once the owner proves it is them; the page again, with the reason, while it is not."""
    match await authority.approve(form.request, form.passphrase):
        case None:
            return page(await authority.pending(form.request), WRONG)
        case redirect:
            return Redirect(redirect, status_code=HTTP_302_FOUND)


##### HANDLERS #####
async def show(
    authority: NamedDependency[Authority], parked: Annotated[str, QueryParameter(name="request")] = ""
) -> Response[str]:
    """The parked request, for the owner to approve or deny."""
    try:
        return page(await authority.pending(parked))
    except UnknownConsentError as exc:
        return gone(exc)


async def decide(
    authority: NamedDependency[Authority],
    data: Annotated[ConsentForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
) -> Response[str] | Redirect:
    """Approve with the passphrase, or deny; either ends at the client unless the passphrase was wrong."""
    try:
        match data.decision:
            case Decision.APPROVE:
                return await approve(authority, data)
            case _:
                return Redirect(await authority.deny(data.request), status_code=HTTP_302_FOUND)
    except UnknownConsentError as exc:
        return gone(exc)


##### CHAINS #####
AUTHORITY_DEPS: Final[dict[str, Provide]] = {
    DepKey.GRAPH.value: Provide(graph, sync_to_thread=False),
    DepKey.AUTHORITY.value: Provide(authority, sync_to_thread=False),
}

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    get(CONSENT_PATH, name="consent.show", include_in_schema=False, dependencies=AUTHORITY_DEPS)(show),
    post(CONSENT_PATH, name="consent.decide", status_code=200, include_in_schema=False, dependencies=AUTHORITY_DEPS)(
        decide
    ),
)
