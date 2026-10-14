"""A stand-in `claude mcp serve`: ListAgents and SendMessage over stdio, answering in the real CLI's JSON shape."""

import json
import sys
from typing import Any

from mcp.server import MCPServer

ROWS: list[dict[str, str]] = [
    {"name": "e-engineer-bc", "ref": "1c9776", "type": "interactive", "status": "busy"},
    {"name": "e-jev-43", "ref": "2bfe88", "type": "interactive", "status": "idle"},
]
LISTING: dict[str, Any] = {
    "listing": "Peer sessions (2)",
    "sections": [
        {
            "kind": "sessions",
            "total": 2,
            "rows": ROWS,
        }
    ],
    "notes": [],
}


def list_agents() -> str:
    return json.dumps(LISTING)


def send_message(to: str, message: str, summary: str = "") -> str:
    known = {row["name"] for row in ROWS}
    return json.dumps({"success": to in known, "message": f"{summary} -> {to}"})


server = MCPServer(name="claude")
server.add_tool(list_agents, name="ListAgents")
server.add_tool(send_message, name="SendMessage")

if __name__ == "__main__" and sys.argv[1:] == ["mcp", "serve"]:
    server.run()
