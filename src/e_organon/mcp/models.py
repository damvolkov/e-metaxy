"""e_organon.mcp.models: what an agent sends each tool — one Struct per tool, its fields the tool's arguments.

The registry tells a client their JSON Schema; the answers are the API's own models, save the readiness one."""

import msgspec

from e_organon.engines.health import ProviderHealth


class NoArgs(msgspec.Struct, frozen=True, kw_only=True):
    """A tool that takes nothing."""


class Status(msgspec.Struct, frozen=True, kw_only=True):
    """Whether the service is ready — every required provider answers — and each provider's verdict."""

    ready: bool
    providers: list[ProviderHealth]
