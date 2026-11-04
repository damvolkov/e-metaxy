"""e_organon.mcp.instructions: what the server tells a client about itself — the door's own words."""

from typing import Final

INSTRUCTIONS: Final[str] = (
    "e-organon's MCP door: the tools are the REST API's routes, served to an agent under the same keys and the same "
    "refusals. Send your key as `Authorization: Bearer <key>`. api_health and api_status say whether the service is up "
    "and which of its providers answer — any caller may ask. The doc tools work on files by path under the vault or the "
    "workspaces, with no model in the loop: doc_convert reads any document into Markdown; doc_inspect lists a PDF's "
    "pages, metadata and form fields; doc_fill writes those fields; doc_merge joins PDFs, doc_split cuts one into page "
    "ranges, doc_render draws pages as PNG — each written file lands in the outbox and its path is the next tool's "
    "input. A refusal is the API's own words: no key, or a key short of the tool's access."
)
