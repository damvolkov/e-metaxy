"""tests/unit/e_organon/mcp/models: what an agent sends each tool, decoded as the engine decodes it — nothing for a tool
that takes nothing, the readiness verdicts round-tripped."""

import msgspec

from e_organon.engines.health import ProviderHealth
from e_organon.mcp.models import NoArgs, Status


async def test_no_args_takes_nothing() -> None:
    assert msgspec.json.decode(b"{}", type=NoArgs) == NoArgs()


async def test_status_round_trips_the_providers_verdicts() -> None:
    verdict = ProviderHealth(name="store", required=True, ok=True, latency=1.5)
    status = Status(ready=True, providers=[verdict])
    assert msgspec.json.decode(msgspec.json.encode(status), type=Status) == status
