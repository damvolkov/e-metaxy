"""core/settings/authority: the authorization server's knobs — METAXY_AUTH_* in the environment or `.env`."""

from datetime import timedelta

from pydantic_settings import SettingsConfigDict

from e_metaxy.core.settings.base import BaseSettings, Secret


class AuthoritySettings(BaseSettings):
    """Who issues the tokens, whose passphrase approves a client, and how long each credential lives."""

    model_config = SettingsConfigDict(env_prefix="METAXY_AUTH_", env_file=".env", extra="ignore", frozen=True)

    issuer: str = "http://127.0.0.1:45190"
    ### the argon2 hash of the owner's passphrase: `e-metaxy owner` makes one; without it no client is ever approved.
    owner_hash: Secret | None = None
    access_ttl: timedelta = timedelta(hours=1)
    refresh_ttl: timedelta = timedelta(days=30)
    code_ttl: timedelta = timedelta(minutes=5)
    consent_ttl: timedelta = timedelta(minutes=10)
    attempts: int = 3
