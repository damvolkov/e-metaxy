"""e_metaxy.api.consent: the one page a person sees — the owner approves or denies a client's authorization.

GET shows the parked request (who asks, where the answer goes back, what it may do) and a passphrase field;
POST decides. Approval or denial ends in a redirect to the client; a wrong passphrase shows the page again
until the attempts run out. The request id travels in the form: it is unguessable, single use and short-lived,
which is what a CSRF token would be. Every value on the page is escaped; the page carries no script."""

import html
from typing import Final
from urllib.parse import urlparse

from beartype import beartype
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import BaseRoute, Route

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


@beartype
class ConsentApi:
    """The consent page over one authority."""

    __slots__ = ("_authority",)

    def __init__(self, authority: Authority) -> None:
        self._authority = authority

    ##### PRIVATE METHODS #####

    @staticmethod
    def _common_page(consent: Consent, error: str = "") -> HTMLResponse:
        escape = html.escape
        scopes = "".join(f"<li>{escape(SCOPES.get(scope, scope))}</li>" for scope in consent.scopes)
        return HTMLResponse(
            PAGE.format(
                client=escape(consent.client_name),
                host=escape(urlparse(consent.redirect_uri).netloc or consent.redirect_uri),
                scopes=scopes,
                error=f'<p class="e">{escape(error)}</p>' if error else "",
                action=escape(CONSENT_PATH),
                request=escape(consent.id),
            ),
            headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
        )

    @staticmethod
    def _common_gone(error: UnknownConsentError) -> HTMLResponse:
        return HTMLResponse(GONE.format(message=html.escape(error.message)), status_code=410)

    async def _decide_approve(self, request: str, passphrase: str) -> Response:
        match await self._authority.approve(request, passphrase):
            case None:
                return self._common_page(await self._authority.pending(request), "That passphrase is not the owner's.")
            case redirect:
                return RedirectResponse(redirect, status_code=302)

    ############################################################

    ##### PUBLIC #####

    async def show(self, request: Request) -> Response:
        try:
            return self._common_page(await self._authority.pending(request.query_params.get("request", "")))
        except UnknownConsentError as exc:
            return self._common_gone(exc)

    async def decide(self, request: Request) -> Response:
        form = await request.form()
        parked, decision = str(form.get("request", "")), str(form.get("decision", ""))
        try:
            match decision:
                case "approve":
                    return await self._decide_approve(parked, str(form.get("passphrase", "")))
                case _:
                    return RedirectResponse(await self._authority.deny(parked), status_code=302)
        except UnknownConsentError as exc:
            return self._common_gone(exc)

    def routes(self) -> list[BaseRoute]:
        return [Route(CONSENT_PATH, self.show, methods=["GET"]), Route(CONSENT_PATH, self.decide, methods=["POST"])]
