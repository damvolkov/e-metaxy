import pytest

from e_metaxy.core.lifespan.mcp import McpState


async def test_sealed_graph_holds_every_section(app) -> None:
    system = app.state.system
    assert {"core", "adapters", "services", "mcp"} <= set(system)
    assert isinstance(system.mcp, McpState)
    with pytest.raises(RuntimeError, match="Sealed"):
        system.late = 1
    with pytest.raises(AttributeError, match="Sealed state has no node"):
        _ = system.typo_of_a_node
