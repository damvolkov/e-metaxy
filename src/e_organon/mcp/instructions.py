"""e_organon.mcp.instructions: what the server tells a client about itself — the door's own words."""

from typing import Final

INSTRUCTIONS: Final[str] = (
    "e-organon's MCP door: the tools are the REST API's routes, served to an agent under the same keys and the same "
    "refusals. Send your key as `Authorization: Bearer <key>`. api_health and api_status say whether the service is up "
    "and which of its providers answer — any caller may ask. doc_convert reads any document under the vault or the workspaces into Markdown, by path, with no model "
    "in the loop. A refusal is the API's own words: no key, or a key short of the tool's access."
)
