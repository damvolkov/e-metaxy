"""e_organon.settings.files: where a tool may read a file from — ORGANON_FILES__*, at `st.e_organon.files`."""

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings


##### SETTINGS #####
class FilesSettings(BaseSettings):
    """ORGANON_FILES__ROOTS: the folders a path argument must sit under — the vault (mounted at its own path in every
    harness, Hermes' upload cache included) and the workspaces."""

    model_config = SettingsConfigDict(env_prefix="ORGANON_FILES__")

    roots: tuple[Path, ...] = (Path("~/.config/memory"), Path("~/workspaces"))
