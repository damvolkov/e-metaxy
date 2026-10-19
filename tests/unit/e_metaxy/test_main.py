"""The assembled app over HTTP: the whole OAuth dance an MCP client performs, then the doors it opens."""

import base64
import hashlib
import secrets
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from fakes import BASE, PASSPHRASE

if TYPE_CHECKING:
    import httpx2

type Bearer = Callable[[str], dict[str, str]]

REDIRECT = "http://127.0.0.1:9999/callback"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


async def sign_in(http: httpx2.AsyncClient) -> dict[str, str]:
    """Register, authorize with PKCE, approve as the owner, exchange the code: the client's tokens."""
    registered = (
        await http.post(
            "/register",
            json={"redirect_uris": [REDIRECT], "client_name": "OpenHuman", "token_endpoint_auth_method": "none"},
        )
    ).json()
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    authorize = await http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": registered["client_id"],
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st-9",
            "scope": "work sessions live",
            "resource": f"{BASE}/mcp",
        },
    )
    consent = urlparse(authorize.headers["location"])
    page = await http.get(f"{consent.path}?{consent.query}")
    assert page.status_code == 200
    assert "OpenHuman" in page.text
    request = query(authorize.headers["location"])["request"]
    wrong = await http.post(consent.path, data={"request": request, "passphrase": "nope", "decision": "approve"})
    assert wrong.status_code == 200
    assert "not the owner" in wrong.text
    approved = await http.post(consent.path, data={"request": request, "passphrase": PASSPHRASE, "decision": "approve"})
    assert approved.status_code == 302
    back = query(approved.headers["location"])
    assert back["state"] == "st-9"
    tokens = await http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": back["code"],
            "redirect_uri": REDIRECT,
            "client_id": registered["client_id"],
            "code_verifier": verifier,
            "resource": f"{BASE}/mcp",
        },
    )
    assert tokens.status_code == 200, tokens.text
    return {**tokens.json(), "client_id": registered["client_id"]}


async def test_main_metadata_advertises_the_authority(http: httpx2.AsyncClient) -> None:
    server = (await http.get("/.well-known/oauth-authorization-server")).json()
    resource = (await http.get("/.well-known/oauth-protected-resource/mcp")).json()
    assert server["issuer"] == BASE
    assert server["registration_endpoint"] == f"{BASE}/register"
    assert resource["resource"] == f"{BASE}/mcp"


async def test_main_mcp_needs_a_token(http: httpx2.AsyncClient) -> None:
    refused = await http.post("/mcp", json=INIT, headers=MCP_HEADERS)
    assert refused.status_code == 401
    assert "resource_metadata" in refused.headers.get("www-authenticate", "")


async def test_main_ops_needs_a_token(http: httpx2.AsyncClient) -> None:
    refused = await http.get("/ops/health")
    assert refused.status_code == 401
    assert "resource_metadata" in refused.headers.get("www-authenticate", "")


async def test_main_ops_refuses_a_forged_token(http: httpx2.AsyncClient) -> None:
    refused = await http.get("/ops/health", headers={"authorization": "Bearer not-a-jwt"})
    assert refused.status_code == 401
    assert "Invalid or expired token" in refused.headers["www-authenticate"]


async def test_main_docs_alias_lands_on_the_root(http: httpx2.AsyncClient) -> None:
    moved = await http.get("/schema/openapi.json")
    assert (moved.status_code, moved.headers["location"]) == (307, "/docs/openapi.json")
    assert "/ops/md" in (await http.get("/docs/openapi.json")).json()["paths"]


async def test_main_ops_needs_the_work_scope(http: httpx2.AsyncClient, bearer: Bearer) -> None:
    assert (await http.get("/ops/health", headers=bearer("sessions"))).status_code == 403
    assert (await http.get("/ops/health", headers=bearer("work"))).status_code == 200


async def test_main_health_is_public(http: httpx2.AsyncClient) -> None:
    assert (await http.get("/health")).json() == {"status": "ok"}


async def test_main_both_doors_carry_a_request_id(http: httpx2.AsyncClient, bearer: Bearer) -> None:
    rest = await http.get("/ops/health", headers=bearer("work"))
    mcp = await http.post("/mcp", json=INIT, headers={**MCP_HEADERS, **bearer("work")})
    assert (rest.status_code, mcp.status_code) == (200, 200)
    assert rest.headers["x-request-id"] != mcp.headers["x-request-id"]


async def test_main_sign_in_opens_mcp_and_ops_then_refresh_and_revoke(http: httpx2.AsyncClient) -> None:
    tokens = await sign_in(http)
    bearer = {"authorization": f"Bearer {tokens['access_token']}"}
    assert (await http.post("/mcp", json=INIT, headers={**MCP_HEADERS, **bearer})).status_code == 200
    assert (await http.get("/ops/health", headers=bearer)).status_code == 200
    foreign = {**MCP_HEADERS, **bearer, "host": "evil.example:45190"}
    assert (await http.post("/mcp", json=INIT, headers=foreign)).status_code == 421
    refreshed = await http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
    ### the SDK's RevocationRequest declares client_secret without a default: a public client sends it empty.
    revoked = await http.post(
        "/revoke",
        data={"token": refreshed.json()["refresh_token"], "client_id": tokens["client_id"], "client_secret": ""},
    )
    assert revoked.status_code == 200
    again = await http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refreshed.json()["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert again.status_code == 400


async def test_main_deny_sends_the_client_access_denied(http: httpx2.AsyncClient) -> None:
    registered = (
        await http.post("/register", json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"})
    ).json()
    authorize = await http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": registered["client_id"],
            "redirect_uri": REDIRECT,
            "code_challenge": "c" * 43,
            "code_challenge_method": "S256",
            "state": "st-d",
        },
    )
    request = query(authorize.headers["location"])["request"]
    denied = await http.post("/oauth/consent", data={"request": request, "decision": "deny"})
    assert query(denied.headers["location"]) == {
        "error": "access_denied",
        "error_description": "the owner did not approve this client",
        "state": "st-d",
    }
    gone = await http.get(f"/oauth/consent?request={request}")
    assert gone.status_code == 410


async def test_main_decide_on_a_gone_request(http: httpx2.AsyncClient) -> None:
    gone = await http.post("/oauth/consent", data={"request": "never-parked", "decision": "approve", "passphrase": "x"})
    assert gone.status_code == 410
