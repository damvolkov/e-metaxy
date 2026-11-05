"""tests/benchmark/conftest: the services behind the live app, faked (`support.app`), as every tier runs them — and what the
catalog's measures read the tool list with."""

from typing import TYPE_CHECKING

import msgspec
import pytest
import tiktoken
from mcp import types

from e_organon.infra.mcp.server import MCPServer
from support.app import coder, keys, psqlpy, queue, queue_database

if TYPE_CHECKING:
    from collections.abc import Sequence

    from e_organon.infra.mcp.models import MCPEntry
    from support.catalog import AtRest, Grown

__all__ = ["coder", "keys", "psqlpy", "queue", "queue_database"]


@pytest.fixture
def at_rest() -> AtRest:
    """What a client pays to list the tools: the JSON of `tools/list` as the MCP server builds it, in bytes and in
    tokens (tiktoken `cl100k_base`, a proxy: no harness tokenizes with it exactly)."""
    encoding = tiktoken.get_encoding("cl100k_base")

    def measure(entries: Sequence[MCPEntry]) -> tuple[int, int]:
        listed = types.ListToolsResult(tools=[MCPServer._list_tool(entry) for entry in entries])
        text = listed.model_dump_json(by_alias=True, exclude_none=True)
        return len(text.encode()), len(encoding.encode(text))

    return measure


@pytest.fixture
def grown() -> Grown:
    """The tools plus `extra` more of their own shapes, cycled under new names (`svc<n>_<word>`): sizes as realistic as
    the real ones'."""

    def grow(entries: Sequence[MCPEntry], extra: int) -> list[MCPEntry]:
        return [
            *entries,
            *(
                msgspec.structs.replace(
                    base,
                    tool=msgspec.structs.replace(
                        base.tool, name=f"svc{i // len(entries)}_{base.tool.name.partition('_')[2]}"
                    ),
                )
                for i in range(extra)
                for base in [entries[i % len(entries)]]
            ),
        ]

    return grow
