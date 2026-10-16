"""scripts/probe.py: drive the live bridge the way an MCP client does — sign in as the owner, then use a tool.

    uv run python scripts/probe.py                                  # sign in, list the tools
    uv run python scripts/probe.py session_find '{"text": "voice"}' # sign in, call one tool with its arguments

The OAuth dance is the real one: dynamic registration, PKCE, the consent page answered with the owner's
passphrase (read from METAXY_PROBE_PASSPHRASE, a file), the code exchanged for a token. Nothing is cached:
every run proves the whole path again."""

import asyncio
import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlparse

import httpx2
import msgspec
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

BASE: Final = os.environ.get("METAXY_PROBE_URL", "http://127.0.0.1:45190")
PASSPHRASE: Final = Path(os.environ.get("METAXY_PROBE_PASSPHRASE", "~/.config/e-metaxy/passphrase")).expanduser()
REDIRECT: Final = "http://127.0.0.1:9/probe"


def query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def show(value: object) -> None:
    print(msgspec.json.format(msgspec.json.encode(value)).decode())


async def sign_in(http: httpx2.AsyncClient) -> str:
    """An access token for every scope, approved on the consent page as the owner."""
    client = (
        (
            await http.post(
                "/register",
                json={"redirect_uris": [REDIRECT], "client_name": "probe", "token_endpoint_auth_method": "none"},
            )
        )
        .raise_for_status()
        .json()["client_id"]
    )
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    parked = await http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "probe",
            "scope": "work sessions live",
            "resource": f"{BASE}/mcp",
        },
    )
    request = query(parked.headers["location"])["request"]
    decided = await http.post(
        "/oauth/consent",
        data={"request": request, "passphrase": PASSPHRASE.read_text().strip(), "decision": "approve"},
    )
    match decided.status_code:
        case 302:
            code = query(decided.headers["location"])["code"]
        case status:
            sys.exit(f"consent refused ({status}): is {PASSPHRASE} the owner's passphrase?")
    tokens = await http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client,
            "code_verifier": verifier,
            "resource": f"{BASE}/mcp",
        },
    )
    return tokens.raise_for_status().json()["access_token"]


async def probe(argv: list[str]) -> int:
    """The exit status: 1 when the tool answered with an error."""
    async with httpx2.AsyncClient(base_url=BASE, timeout=30) as http:
        token = await sign_in(http)
    print(f"signed in at {BASE}", file=sys.stderr)
    bearer = httpx2.AsyncClient(headers={"authorization": f"Bearer {token}"}, timeout=httpx2.Timeout(30, read=300))
    async with bearer, Client(streamable_http_client(f"{BASE}/mcp", http_client=bearer)) as client:
        match argv:
            case []:
                show([{"name": tool.name, "title": tool.title} for tool in (await client.list_tools()).tools])
                return 0
            case [tool, *rest]:
                result = await client.call_tool(tool, msgspec.json.decode(rest[0]) if rest else {})
                show(result.structured_content or [block.model_dump() for block in result.content])
                return int(result.is_error)


if __name__ == "__main__":
    sys.exit(asyncio.run(probe(sys.argv[1:])))
