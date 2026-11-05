"""tests/benchmark/e_organon/catalog: what the tool list costs a client at rest — the door's real registry, with and without
the bridge, and grown by 150 tools of the same shapes. Measured in the JSON bytes of `tools/list` and in tokens
(`cl100k_base`, a proxy); `docs/catalog.md` holds the numbers and the decision they feed. Slow: the encoding is fetched
on first use (`make test TESTARGS="-m slow"`)."""

from typing import TYPE_CHECKING, Final

import pytest

from e_organon.infra.mcp.registry import MCPRegistry
from e_organon.mcp.registry import CORE, ROUTES

if TYPE_CHECKING:
    from support.catalog import AtRest, Grown

### a server's tools at rest should stay under 5 000 tokens (2.5 % of a 200 000-token window); the day it does not, the
### catalog (`organon/find`) and the harness's own deferral carry the weight, and profiles are asked again.
BUDGET: Final[int] = 5_000
EXTRA: Final[int] = 150


@pytest.mark.slow
@pytest.mark.parametrize("routes", [CORE, ROUTES], ids=["core", "with-tekton"])
async def test_catalog_real_registry_stays_under_the_budget(at_rest: AtRest, routes: tuple) -> None:
    tools = list(MCPRegistry(routes))
    size, tokens = at_rest(tools)
    print(f"{len(tools)} tools: {size} bytes, {tokens} tokens")  # noqa: T201 — the measure is the product
    assert tokens <= BUDGET


@pytest.mark.slow
async def test_catalog_150_more_tools_cost_about_what_the_real_ones_each_do(at_rest: AtRest, grown: Grown) -> None:
    real = list(MCPRegistry(ROUTES))
    _, base = at_rest(real)
    size, tokens = at_rest(grown(real, EXTRA))
    print(f"{len(real) + EXTRA} tools: {size} bytes, {tokens} tokens")  # noqa: T201 — the measure is the product
    assert base / len(real) * 0.8 <= (tokens - base) / EXTRA <= base / len(real) * 1.2
