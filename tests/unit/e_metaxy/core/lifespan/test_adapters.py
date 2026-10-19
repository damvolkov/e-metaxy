import pytest

from e_metaxy.adapters.openhuman import OpenHumanAdapter
from e_metaxy.core.lifespan.adapters import AdaptersState, callers
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.metaxy import MetaxySettings


@pytest.mark.parametrize(("token", "expected"), [(None, []), (Secret("core"), ["openhuman"])], ids=["off", "on"])
def test_adapters_callers(token: Secret | None, expected: list[str]) -> None:
    built = callers(MetaxySettings(openhuman_token=token))
    assert (list(built), all(isinstance(n, OpenHumanAdapter) for n in built.values())) == (expected, True)


async def test_adapters_section_opens_and_closes(app) -> None:
    edges = app.state.system.adapters
    assert isinstance(edges, AdaptersState)
    assert [edge.name for edge in edges] == ["sqlite", "claude", "anytomd", "docling"]
    await edges.store.get("anything")
