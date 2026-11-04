"""core/settings/metaxy: the bridge's knobs — METAXY_* in the environment or `.env`."""

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from e_metaxy.core.settings.base import BaseSettings


class MetaxySettings(BaseSettings):
    """Where the bridge listens, what it reads, and how many runs at once."""

    model_config = SettingsConfigDict(env_prefix="METAXY_", env_file=".env", extra="ignore", frozen=True)

    host: str = "127.0.0.1"
    port: int = 45190
    profiles: Path = Path("profiles.yaml")
    ### where short project names ("e-voice") are looked up, one and two levels deep.
    workspaces: Path = Path("~/workspaces")
    ledger: Path = Path("~/.local/share/e-metaxy/ledger.db")
    limit: int = 4
    claude: str = "claude"
