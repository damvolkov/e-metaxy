import pytest

from e_metaxy.core.crypto import Crypto
from e_metaxy.core.lifespan.services import ServicesState, owner
from e_metaxy.core.settings.authority import AuthoritySettings
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.crypto import CryptoSettings
from e_metaxy.models.error import OwnerUnsetError


def test_services_owner_refuses_to_start_without_a_hash() -> None:
    with pytest.raises(OwnerUnsetError):
        owner(Crypto(CryptoSettings(secret=Secret("k" * 48))), AuthoritySettings(owner_hash=None))


async def test_services_section_is_built(app) -> None:
    system = app.state.system
    assert isinstance(system.services, ServicesState)
    assert system.services.policy.resource == f"{system.services.policy.issuer}/mcp"
    assert "research" in system.services.profiles
