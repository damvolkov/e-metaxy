"""MCP fixtures: the real MCP server, tools registered by the composition root, over a fake-coder bridge.

The in-memory client opens anyio scopes that must close in the task that opened them, so the fixture hands
out a context factory and each test opens its own connection."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from fakes import DONE_SCRIPT, Connect, ScriptedCoder, Wire
from mcp import Client
from mcp.server import MCPServer

from e_metaxy.main import INSTRUCTIONS
from e_metaxy.mcp.tools import BridgeTools, register

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from e_metaxy.models.profile import Profile


@pytest.fixture
def connect(wire: Wire, book: Mapping[str, Profile]) -> Connect:
    @asynccontextmanager
    async def opened() -> AsyncGenerator[Client]:
        async with wire(ScriptedCoder(DONE_SCRIPT)) as bridge:
            server = register(MCPServer(name="e-metaxy", instructions=INSTRUCTIONS), BridgeTools(bridge), book)
            async with Client(server) as client:
                yield client

    return opened
