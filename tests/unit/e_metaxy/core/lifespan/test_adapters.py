from e_metaxy.core.lifespan.adapters import AdaptersState


async def test_adapters_section_opens_and_closes(app) -> None:
    edges = app.state.system.adapters
    assert isinstance(edges, AdaptersState)
    assert [edge.name for edge in edges] == ["sqlite", "claude", "anytomd", "docling"]
    await edges.store.get("anything")
