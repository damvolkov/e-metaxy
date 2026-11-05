"""tests/unit/e_organon/api/lifespan/infra: the infra singletons loaded once and mirrored as the `shared` section."""

from typing import TYPE_CHECKING

from e_organon.api.lifespan.infra import SharedState
from e_organon.infra import settings as settings_module
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st

if TYPE_CHECKING:
    from litestar.testing import TestClient


def test_infra_shared_section_holds_the_logger_never_the_settings(client: TestClient) -> None:
    shared = client.app.state.system.shared
    assert (isinstance(shared, SharedState), shared.logger is logger, hasattr(shared, "settings")) == (
        True,
        True,
        False,
    )


def test_infra_settings_are_one_instance(client: TestClient) -> None:
    """Read once, at import: the module's instance is the one every reader shares."""
    assert settings_module.settings is st
