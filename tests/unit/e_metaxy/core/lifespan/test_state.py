import pytest
from litestar import Litestar

from e_metaxy.core.lifespan.state import AppState


def test_state_of_refuses_a_foreign_state() -> None:
    with pytest.raises(TypeError, match="create_app owns the state"):
        AppState.of(Litestar())
