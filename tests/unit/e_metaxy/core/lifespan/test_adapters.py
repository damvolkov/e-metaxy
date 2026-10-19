import pytest

from e_metaxy.adapters.discord import DiscordAdapter
from e_metaxy.adapters.openhuman import OpenHumanAdapter
from e_metaxy.core.lifespan.adapters import AdaptersState, callers
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.metaxy import MetaxySettings


@pytest.mark.parametrize(
    ("token", "webhook", "expected"),
    [
        (None, None, {}),
        (Secret("core"), None, {"openhuman": OpenHumanAdapter}),
        (None, Secret("https://discord.test/hook"), {"discord": DiscordAdapter}),
        (
            Secret("core"),
            Secret("https://discord.test/hook"),
            {"openhuman": OpenHumanAdapter, "discord": DiscordAdapter},
        ),
    ],
    ids=["off", "openhuman", "discord", "both"],
)
def test_adapters_callers(token: Secret | None, webhook: Secret | None, expected: dict[str, type]) -> None:
    built = callers(MetaxySettings(openhuman_token=token, discord_webhook=webhook))
    assert {name: type(n) for name, n in built.items()} == expected


async def test_adapters_section_opens_and_closes(app) -> None:
    edges = app.state.system.adapters
    assert isinstance(edges, AdaptersState)
    assert [edge.name for edge in edges] == ["sqlite", "claude", "anytomd", "docling"]
    await edges.store.get("anything")
