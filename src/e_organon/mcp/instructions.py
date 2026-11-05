"""e_organon.mcp.instructions: what the server tells a client about itself — the door's own words."""

from typing import Final

INSTRUCTIONS: Final[str] = (
    "e-organon's MCP door: the tools are the REST API's routes, served to an agent under the same keys and the same "
    "refusals. Send your key as `Authorization: Bearer <key>`. api_health and api_status say whether the service is up "
    "and which of its providers answer — any caller may ask. The doc tools work on files by path under the vault or the "
    "workspaces, with no model in the loop: doc_convert reads any document into Markdown; doc_inspect lists a PDF's "
    "pages, metadata and form fields; doc_fill writes those fields; doc_merge joins PDFs, doc_split cuts one into page "
    "ranges, doc_render draws pages as PNG, doc_stamp draws an image or a text on one (at a field, a text anchor or a box), "
    "doc_signature places a photographed signature — each written file lands in the outbox and its path is the next tool's "
    "input. image_cutout lifts the ink of a photographed signature into a transparent PNG. organon_find ranks these tools against a need, with their schemas. A doc tool queued over REST with `Prefer: respond-async` is a job: organon_job reads it (wait up to 25 s; its "
    "progress has the steps so far, then `done` or `failed`) and organon_cancel stops it. "
    "The tekton tools are the bridge to Claude Code on this machine: tekton_start runs a prompt in a project "
    "under a profile and answers at once with the task, tekton_status watches it (wait up to 25 s), tekton_tasks lists "
    "them, tekton_cancel stops one; tekton_find, tekton_read and tekton_update locate, read and name its recorded "
    "sessions, and tekton_start with a session continues one; tekton_catalog lists a project's commands, skills and "
    "agents; tekton_peers and tekton_send reach the sessions open in a terminal; tekton_eng runs the user's `eng` "
    "message through its grammar. A refusal is the API's own words: no key, or a key short of the tool's access."
)
