"""e_metaxy.config.metaxy: the bridge's knobs — METAXY_* in the environment or `.env`."""

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from core.settings.base import BaseSettings, Secret


class MetaxySettings(BaseSettings):
    """Where the bridge listens, what it reads, how many runs at once, and whom it calls back."""

    model_config = SettingsConfigDict(env_prefix="METAXY_", env_file=".env", extra="ignore", frozen=True)

    host: str = "127.0.0.1"
    port: int = 45190
    token: Secret | None = None
    profiles: Path = Path("profiles.yaml")
    ledger: Path = Path("~/.local/share/e-metaxy/ledger.db")
    limit: int = 4
    claude: str = "claude"
    openhuman_url: str = "http://127.0.0.1:7788/rpc"
    openhuman_token: Secret | None = None
