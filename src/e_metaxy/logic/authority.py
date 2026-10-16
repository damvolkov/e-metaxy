"""e_metaxy.logic.authority: the bridge as its own OAuth 2.1 authorization server, the way MCP asks.

The MCP SDK serves the protocol — metadata, dynamic registration, /authorize, /token, /revoke, the bearer gate —
and calls this provider for every decision. Clients register themselves (public, PKCE); an authorization waits
on the consent page until the owner proves it is them; codes and refresh tokens are opaque, single use and
stored by their SHA-256; access tokens are JWTs the crypto engine signs and verifies, bound to the MCP resource.

The provider knows ports and the crypto engine only: where the records live, who the owner is and which keys
sign are the composition root's business."""

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any, Final

import msgspec
import structlog
from beartype import beartype
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    IdentityAssertionParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from e_metaxy.adapters.ports import StorePort
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.errors import TokenError as CryptoTokenError
from e_metaxy.logic.ports import OwnerPort
from e_metaxy.models.auth import Consent, Grant, Policy, Renewal, Scope
from e_metaxy.models.error import UnknownConsentError

log = structlog.get_logger()

CLIENT: Final = "oauth:client:"
CONSENT: Final = "oauth:consent:"
CODE: Final = "oauth:code:"
REFRESH: Final = "oauth:refresh:"
SUBJECT: Final = "owner"
CONSENT_PATH: Final = "/oauth/consent"


@beartype
class Authority:
    """Registers clients, parks authorizations for the owner, and issues, rotates, verifies and revokes tokens."""

    __slots__ = ("_crypto", "_owner", "_policy", "_store")

    def __init__(self, *, crypto: Crypto, store: StorePort, owner: OwnerPort, policy: Policy) -> None:
        self._crypto = crypto
        self._store = store
        self._owner = owner
        self._policy = policy

    ##### PRIVATE METHODS #####

    @staticmethod
    def _common_digest(token: str) -> str:
        ### a code or refresh token carries 256 bits of entropy: an unkeyed hash is a sufficient lookup key.
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _common_expiry(ttl: Any) -> datetime:
        return datetime.now(UTC) + ttl

    async def _common_put(self, key: str, record: msgspec.Struct) -> None:
        await self._store.set(key, msgspec.json.encode(record, enc_hook=Consent.enc_hook))

    async def _common_take[T: msgspec.Struct](self, key: str, kind: type[T]) -> T | None:
        match await self._store.get(key):
            case None:
                return None
            case raw:
                return Consent.convert(msgspec.json.decode(raw), kind)

    async def _consent_pending(self, request: str) -> Consent:
        match await self._common_take(CONSENT + request, Consent):
            case Consent() as consent if not consent.expired:
                return consent
            case _:
                await self._store.delete(CONSENT + request)
                raise UnknownConsentError(request)

    def _consent_denied(self, consent: Consent) -> str:
        return construct_redirect_uri(
            consent.redirect_uri,
            error="access_denied",
            error_description="the owner did not approve this client",
            state=consent.state,
        )

    async def _exchange_issue(
        self, client_id: str, scopes: tuple[str, ...], resource: str | None, subject: str
    ) -> OAuthToken:
        """A signed access token bound to the resource, and a fresh opaque refresh token stored by its digest."""
        policy = self._policy
        access = self._crypto.create_token(
            {
                "iss": policy.issuer,
                "aud": resource or policy.resource,
                "sub": subject,
                "client_id": client_id,
                "scope": " ".join(scopes),
                "jti": secrets.token_urlsafe(16),
                "iat": int(datetime.now(UTC).timestamp()),
            },
            expires_in=policy.access_ttl,
        )
        refresh = secrets.token_urlsafe(32)
        renewal = Renewal(
            client_id=client_id,
            scopes=scopes,
            resource=resource,
            subject=subject,
            expires=self._common_expiry(policy.refresh_ttl),
        )
        await self._common_put(REFRESH + self._common_digest(refresh), renewal)
        return OAuthToken(
            access_token=access,
            expires_in=int(policy.access_ttl.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    ############################################################

    ##### CLIENTS #####

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        match await self._store.get(CLIENT + client_id):
            case None:
                return None
            case raw:
                return OAuthClientInformationFull.model_validate_json(raw)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self._store.set(CLIENT + str(client_info.client_id), client_info.model_dump_json().encode())
        log.info("OAUTH_CLIENT_REGISTERED", client=client_info.client_id, name=client_info.client_name)

    ##### AUTHORIZATION #####

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Park the request and send the user agent to the consent page; the owner decides there."""
        consent = Consent(
            id=secrets.token_urlsafe(24),
            client_id=str(client.client_id),
            client_name=client.client_name or str(client.client_id),
            redirect_uri=str(params.redirect_uri),
            redirect_explicit=params.redirect_uri_provided_explicitly,
            scopes=tuple(params.scopes or [scope.value for scope in Scope]),
            state=params.state,
            code_challenge=params.code_challenge,
            resource=params.resource,
            expires=self._common_expiry(self._policy.consent_ttl),
        )
        await self._common_put(CONSENT + consent.id, consent)
        return construct_redirect_uri(f"{self._policy.issuer}{CONSENT_PATH}", request=consent.id)

    async def pending(self, request: str) -> Consent:
        """The parked request the consent page shows; an unknown or expired one raises."""
        return await self._consent_pending(request)

    async def approve(self, request: str, secret: str) -> str | None:
        """The client's redirect with a fresh code once the owner proves it is them; `None` asks again, and the
        last allowed miss turns into the client's `access_denied`."""
        consent = await self._consent_pending(request)
        match await self._owner.admits(secret):
            case True:
                await self._store.delete(CONSENT + request)
                code = secrets.token_urlsafe(32)
                grant = Grant(
                    client_id=consent.client_id,
                    scopes=consent.scopes,
                    code_challenge=consent.code_challenge,
                    redirect_uri=consent.redirect_uri,
                    redirect_explicit=consent.redirect_explicit,
                    resource=consent.resource,
                    subject=SUBJECT,
                    expires=self._common_expiry(self._policy.code_ttl),
                )
                await self._common_put(CODE + self._common_digest(code), grant)
                log.info("OAUTH_APPROVED", client=consent.client_id, scopes=consent.scopes)
                return construct_redirect_uri(consent.redirect_uri, code=code, state=consent.state)
            case False if consent.attempts + 1 >= self._policy.attempts:
                log.warning("OAUTH_REFUSED", client=consent.client_id, attempts=consent.attempts + 1)
                return await self.deny(request)
            case _:
                await self._common_put(
                    CONSENT + request, msgspec.structs.replace(consent, attempts=consent.attempts + 1)
                )
                return None

    async def deny(self, request: str) -> str:
        """The client's redirect with `access_denied`; the request is gone."""
        consent = await self._consent_pending(request)
        await self._store.delete(CONSENT + request)
        return self._consent_denied(consent)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        match await self._common_take(CODE + self._common_digest(authorization_code), Grant):
            case Grant() as grant if grant.client_id == client.client_id:
                return AuthorizationCode(
                    code=authorization_code,
                    scopes=list(grant.scopes),
                    expires_at=grant.expires.timestamp(),
                    client_id=grant.client_id,
                    code_challenge=grant.code_challenge,
                    redirect_uri=AnyUrl(grant.redirect_uri),
                    redirect_uri_provided_explicitly=grant.redirect_explicit,
                    resource=grant.resource,
                    subject=grant.subject,
                )
            case _:
                return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        await self._store.delete(CODE + self._common_digest(authorization_code.code))
        return await self._exchange_issue(
            str(client.client_id),
            tuple(authorization_code.scopes),
            authorization_code.resource,
            authorization_code.subject or SUBJECT,
        )

    ##### REFRESH #####

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        match await self._common_take(REFRESH + self._common_digest(refresh_token), Renewal):
            case Renewal() as renewal if renewal.client_id == client.client_id and datetime.now(UTC) < renewal.expires:
                return RefreshToken(
                    token=refresh_token,
                    client_id=renewal.client_id,
                    scopes=list(renewal.scopes),
                    expires_at=int(renewal.expires.timestamp()),
                    resource=renewal.resource,
                    subject=renewal.subject,
                )
            case _:
                return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        """Rotation: the presented refresh token dies with this exchange; narrower scopes may be asked for."""
        await self._store.delete(REFRESH + self._common_digest(refresh_token.token))
        kept = (
            tuple(scope for scope in scopes if scope in refresh_token.scopes) if scopes else tuple(refresh_token.scopes)
        )
        return await self._exchange_issue(
            str(client.client_id), kept, refresh_token.resource, refresh_token.subject or SUBJECT
        )

    ##### ACCESS #####

    async def load_access_token(self, token: str) -> AccessToken | None:
        """The bearer's claims once the crypto engine verified signature, expiry, issuer and audience."""
        policy = self._policy
        try:
            claims = self._crypto.verify_token(token, issuer=policy.issuer, audience=policy.resource)
        except CryptoTokenError:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "")),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=claims.get("exp"),
            resource=policy.resource,
            subject=str(claims.get("sub", "")),
            claims={"iss": claims.get("iss")},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """A refresh token is deleted; an access token is short-lived and dies at its `exp`."""
        match token:
            case RefreshToken():
                await self._store.delete(REFRESH + self._common_digest(token.token))
            case _:
                return

    async def exchange_identity_assertion(
        self, client: OAuthClientInformationFull, params: IdentityAssertionParams
    ) -> OAuthToken:
        """No identity provider vouches for anyone here: only the owner's consent issues tokens."""
        log.warning("OAUTH_ASSERTION_REFUSED", client=client.client_id, asserted=bool(params.assertion))
        raise TokenError(error="unsupported_grant_type", error_description="identity assertions are not accepted")
