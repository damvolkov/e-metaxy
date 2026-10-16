"""The authority over a real ledger and the real crypto engine: consent, codes, tokens, rotation, revocation."""

from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AuthorizationParams, IdentityAssertionParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from e_metaxy.adapters.owner.passphrase import PassphraseOwner
from e_metaxy.config.authority import AuthoritySettings
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.settings import Secret
from e_metaxy.core.settings.crypto import CryptoSettings
from e_metaxy.logic.authority import CONSENT_PATH, Authority
from e_metaxy.models.error import UnknownConsentError

if TYPE_CHECKING:
    from e_metaxy.adapters.sqlite import SQLiteAdapter

ISSUER = "http://127.0.0.1:45190"
PASSPHRASE = "correct horse battery staple"
REDIRECT = "http://127.0.0.1:9999/callback"


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


@pytest.fixture
def crypto() -> Crypto:
    return Crypto(CryptoSettings(secret=Secret("s" * 48)))


@pytest.fixture
async def authority(crypto: Crypto, ledger: SQLiteAdapter) -> Authority:
    hashed = await crypto.hash_password(PASSPHRASE)
    settings = AuthoritySettings(issuer=ISSUER, owner_hash=Secret(hashed), attempts=2)
    return Authority(crypto=crypto, store=ledger, owner=PassphraseOwner(crypto, hashed), policy=settings.policy)


@pytest.fixture
def client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="oh", client_name="OpenHuman", redirect_uris=[AnyUrl(REDIRECT)], token_endpoint_auth_method="none"
    )


@pytest.fixture
def params() -> AuthorizationParams:
    return AuthorizationParams(
        state="st-1",
        scopes=["work", "sessions"],
        code_challenge="c" * 43,
        redirect_uri=AnyUrl(REDIRECT),
        redirect_uri_provided_explicitly=True,
        resource=f"{ISSUER}/mcp",
    )


async def parked(authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
    await authority.register_client(client)
    target = await authority.authorize(client, params)
    assert urlparse(target).path == CONSENT_PATH
    return query(target)["request"]


async def approved(authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
    redirect = await authority.approve(await parked(authority, client, params), PASSPHRASE)
    assert redirect is not None
    return query(redirect)["code"]


async def test_authority_client_roundtrip(authority: Authority, client: OAuthClientInformationFull) -> None:
    await authority.register_client(client)
    assert await authority.get_client("oh") == client
    assert await authority.get_client("nobody") is None


async def test_authority_authorize_parks_for_the_owner(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    consent = await authority.pending(await parked(authority, client, params))
    assert (consent.client_name, consent.scopes, consent.state) == ("OpenHuman", ("work", "sessions"), "st-1")


async def test_authority_authorize_without_scopes_asks_for_all(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    unscoped = params.model_copy(update={"scopes": None})
    consent = await authority.pending(await parked(authority, client, unscoped))
    assert consent.scopes == ("work", "sessions", "live")


async def test_authority_approve_issues_a_code_with_state(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    redirect = await authority.approve(await parked(authority, client, params), PASSPHRASE)
    assert redirect is not None
    assert redirect.startswith(REDIRECT)
    assert query(redirect)["state"] == "st-1"
    assert query(redirect)["code"]


async def test_authority_wrong_passphrase_asks_again_then_denies(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    request = await parked(authority, client, params)
    assert await authority.approve(request, "guess") is None
    assert (await authority.pending(request)).attempts == 1
    denied = await authority.approve(request, "guess again")
    assert denied is not None
    assert query(denied)["error"] == "access_denied"
    assert query(denied)["state"] == "st-1"
    with pytest.raises(UnknownConsentError):
        await authority.pending(request)


async def test_authority_deny_redirects_access_denied(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    request = await parked(authority, client, params)
    assert query(await authority.deny(request))["error"] == "access_denied"
    with pytest.raises(UnknownConsentError):
        await authority.approve(request, PASSPHRASE)


async def test_authority_consent_expires(
    crypto: Crypto, ledger: SQLiteAdapter, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    hashed = await crypto.hash_password(PASSPHRASE)
    stale = Authority(
        crypto=crypto,
        store=ledger,
        owner=PassphraseOwner(crypto, hashed),
        policy=AuthoritySettings(issuer=ISSUER, consent_ttl=timedelta(seconds=-1)).policy,
    )
    with pytest.raises(UnknownConsentError):
        await stale.pending(await parked(stale, client, params))


async def test_authority_code_is_bound_to_its_client_and_single_use(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    code = await approved(authority, client, params)
    other = client.model_copy(update={"client_id": "intruder"})
    assert await authority.load_authorization_code(other, code) is None
    loaded = await authority.load_authorization_code(client, code)
    assert loaded is not None
    assert loaded.scopes == ["work", "sessions"]
    assert loaded.subject == "owner"
    await authority.exchange_authorization_code(client, loaded)
    assert await authority.load_authorization_code(client, code) is None


async def test_authority_access_token_verifies_bound_to_resource(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    code = await approved(authority, client, params)
    loaded = await authority.load_authorization_code(client, code)
    assert loaded is not None
    token = await authority.exchange_authorization_code(client, loaded)
    access = await authority.load_access_token(token.access_token)
    assert access is not None
    assert (access.client_id, access.scopes, access.resource) == ("oh", ["work", "sessions"], f"{ISSUER}/mcp")
    assert await authority.load_access_token(token.access_token[:-2] + "xx") is None


async def test_authority_access_token_from_another_issuer_refused(
    crypto: Crypto, ledger: SQLiteAdapter, authority: Authority
) -> None:
    foreign = crypto.create_token(
        {"iss": "http://elsewhere", "aud": f"{ISSUER}/mcp", "scope": "work"}, expires_in=timedelta(minutes=5)
    )
    assert await authority.load_access_token(foreign) is None


async def test_authority_refresh_rotates_and_narrows(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    code = await approved(authority, client, params)
    loaded = await authority.load_authorization_code(client, code)
    assert loaded is not None
    first = await authority.exchange_authorization_code(client, loaded)
    assert first.refresh_token is not None
    refresh = await authority.load_refresh_token(client, first.refresh_token)
    assert refresh is not None
    second = await authority.exchange_refresh_token(client, refresh, ["work", "live"])
    assert second.scope == "work"
    assert await authority.load_refresh_token(client, first.refresh_token) is None
    assert second.refresh_token is not None
    assert await authority.load_refresh_token(client, second.refresh_token) is not None


async def test_authority_revoke_refresh(
    authority: Authority, client: OAuthClientInformationFull, params: AuthorizationParams
) -> None:
    code = await approved(authority, client, params)
    loaded = await authority.load_authorization_code(client, code)
    assert loaded is not None
    token = await authority.exchange_authorization_code(client, loaded)
    assert token.refresh_token is not None
    refresh = await authority.load_refresh_token(client, token.refresh_token)
    assert refresh is not None
    await authority.revoke_token(refresh)
    assert await authority.load_refresh_token(client, token.refresh_token) is None
    access = await authority.load_access_token(token.access_token)
    assert access is not None
    await authority.revoke_token(access)


async def test_authority_identity_assertion_refused(authority: Authority, client: OAuthClientInformationFull) -> None:
    with pytest.raises(TokenError):
        await authority.exchange_identity_assertion(client, IdentityAssertionParams(assertion="a.b.c"))
