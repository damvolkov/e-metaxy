"""e_metaxy.config.authority: the authorization server's knobs — METAXY_AUTH_* in the environment or `.env`."""

from datetime import timedelta

from pydantic_settings import SettingsConfigDict

from e_metaxy.core.settings.base import BaseSettings, Secret
from e_metaxy.models.auth import Policy


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

    @property
    def policy(self) -> Policy:
        """Everything the authority needs, the owner's hash excepted: that goes to the owner alone."""
        return Policy(
            issuer=self.issuer,
            access_ttl=self.access_ttl,
            refresh_ttl=self.refresh_ttl,
            code_ttl=self.code_ttl,
            consent_ttl=self.consent_ttl,
            attempts=self.attempts,
        )

    @property
    def resource(self) -> str:
        return self.policy.resource
