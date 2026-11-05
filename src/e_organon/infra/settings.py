"""infra/settings: the one `Settings` — every cluster of `infra/config`, read once, at import.

The environment, `.env`, the secrets folder and the config file are read here, validated, and frozen. Only the
composition root imports `settings` (`from e_organon.infra.settings import settings as st`) and hands each provider,
engine, processor and service its typed values; everything below takes plain keyword arguments."""

from e_organon.infra.config.agent import AgentSettings
from e_organon.infra.config.api import ApiSettings
from e_organon.infra.config.cli import CliSettings
from e_organon.infra.config.darts import DartsSettings
from e_organon.infra.config.engines import EngineSettings
from e_organon.infra.config.infra import InfraSettings
from e_organon.infra.config.mcp import McpSettings
from e_organon.infra.config.processors import ProcessorSettings
from e_organon.infra.config.providers import ProviderSettings
from e_organon.infra.config.services import ServiceSettings
from e_organon.infra.config.theme import ThemeSettings
from e_organon.infra.config.ui import UiSettings


##### SETTINGS #####
class Settings(
    InfraSettings,
    ProviderSettings,
    EngineSettings,
    ProcessorSettings,
    ServiceSettings,
    ApiSettings,
    McpSettings,
    CliSettings,
    AgentSettings,
    DartsSettings,
    ThemeSettings,
    UiSettings,
):
    """Every cluster, one contract."""


settings = Settings()
