"""e_metaxy.models.auth: what the authorization server parks and remembers between the redirects.

A `Consent` waits for the owner on the consent page; a `Grant` is an authorization code's record; a `Renewal`
is a refresh token's. Codes and refresh tokens are opaque: the store keys them by their SHA-256, so a leaked
ledger yields no usable token. Access tokens are never stored — they are JWTs the crypto engine verifies."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from e_metaxy.core.struct import CheckedStruct


##### ENUMS #####
class Scope(StrEnum):
    """What a token lets its client do: run and watch work, read and edit sessions, talk to live sessions."""

    WORK = "work"
    SESSIONS = "sessions"
    LIVE = "live"


##### POLICY #####
class Policy(CheckedStruct, frozen=True, kw_only=True):
    """Who issues the tokens and how long each credential lives — the settings' view the authority reads."""

    issuer: str
    access_ttl: timedelta
    refresh_ttl: timedelta
    code_ttl: timedelta
    consent_ttl: timedelta
    attempts: int

    @property
    def resource(self) -> str:
        """The protected resource (RFC 8707): the MCP endpoint every token is bound to."""
        return f"{self.issuer}/mcp"


##### RECORDS #####
class Consent(CheckedStruct, frozen=True, kw_only=True):
    """An authorization request parked until the owner approves it on the consent page."""

    id: str
    client_id: str
    client_name: str
    redirect_uri: str
    redirect_explicit: bool
    scopes: tuple[str, ...]
    state: str | None = None
    code_challenge: str
    resource: str | None = None
    expires: datetime
    attempts: int = 0

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) >= self.expires


class Grant(CheckedStruct, frozen=True, kw_only=True):
    """An authorization code's record: what the owner approved, for which client, until when."""

    client_id: str
    scopes: tuple[str, ...]
    code_challenge: str
    redirect_uri: str
    redirect_explicit: bool
    resource: str | None = None
    subject: str
    expires: datetime


class Renewal(CheckedStruct, frozen=True, kw_only=True):
    """A refresh token's record: single use, rotated on every exchange."""

    client_id: str
    scopes: tuple[str, ...]
    resource: str | None = None
    subject: str
    expires: datetime
