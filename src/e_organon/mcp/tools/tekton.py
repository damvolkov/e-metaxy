"""e_organon.mcp.tools.tekton: the tekton/ section as tools — the twin of `api/router/tekton`, whose very handlers they are.

The bridge between polymath harnesses and Claude Code on this machine. Work runs in the background: `tekton_start`
answers at once with the task, `tekton_status` watches it, `tekton_tasks` shows what is running, `tekton_cancel` stops
it. A session is Claude Code's conversation, the same one `claude --resume` opens: `tekton_find` locates it,
`tekton_read` shows where it stopped, `tekton_update` names it, and `tekton_start` with its id continues it.
`tekton_catalog` says which commands, skills and agents a project offers; `tekton_peers` and `tekton_send` reach the
sessions open in a terminal; `tekton_eng` runs the user's `eng` message through its grammar. The MCP engine asks for
JSON, so a tool always answers in batch: the result, or the `Failed` reason as its error."""

from typing import Final

from litestar.handlers import HTTPRouteHandler

from e_organon.api.router import tekton as router
from e_organon.infra.auth.models import Access
from e_organon.infra.mcp.models import MCPTool
from e_organon.mcp.refusals import REFUSALS

##### TOOLS — what a client is told #####
ENG: Final = MCPTool(
    name="tekton_eng",
    title="Run an eng order",
    description=(
        "Pass the user's `eng` message exactly as typed, prefix included; the grammar is parsed here, never by you. "
        "`project`: the project the conversation is about, for an order that names none; `profile`: what a new run may "
        "do. Grammar: `eng [project:] <order>` new session · `eng @ref: <order>` continue · `eng @ref+: <order>` "
        "branch · `eng @ref?` where it stopped · `eng @ref = <title>` rename · `eng ls [project]` sessions · `eng ps` "
        "tasks · `eng stop <task>`. `ref` is a session id, its first 8 characters or its exact title. Answers "
        "`verb` and `result`."
    ),
    read_only=False,
)
START: Final = MCPTool(
    name="tekton_start",
    title="Start work in Claude Code",
    description=(
        "Run a prompt in Claude Code on this machine, with the user's whole setup (CLAUDE.md, skills, commands, "
        "agents, hooks). Returns at once with `id` (the task) and, once known, `session`. `prompt`: plain words, or a "
        'command/skill such as "/research vLLM sleep mode" (see tekton_catalog). `project`: a short name ("e-voice") '
        "or a path. `profile`: what the run may do — the profiles are the service's book (profiles.yaml): `code` by "
        "default, a refusal lists the declared ones. `session`: continue that conversation instead of starting one "
        "(its id, the first 8 characters of it, or its exact title); `fork`: branch it. Next: tekton_status with "
        "`id`; keep `session` to continue later."
    ),
    read_only=False,
)
STATUS: Final = MCPTool(
    name="tekton_status",
    title="Check a task",
    description=(
        "A task's state (running, done, failed, cancelled), its session, final `result`, `error`, cost and turns. "
        "`wait` (seconds, at most 25) returns as soon as it ends instead of right away."
    ),
)
TASKS: Final = MCPTool(
    name="tekton_tasks",
    title="List tasks",
    description="The newest tasks first — what is running, what finished; `state` narrows to one state.",
)
CANCEL: Final = MCPTool(
    name="tekton_cancel",
    title="Cancel a task",
    description="Interrupt a running task; a finished one comes back unchanged. Its session can be continued.",
    read_only=False,
    destructive=True,
)
CATALOG: Final = MCPTool(
    name="tekton_catalog",
    title="What Claude Code offers in a project",
    description=(
        "The slash commands, skills and agents Claude Code has in `project` (short name or path; empty means the "
        'workspace root). Use a command or skill as a tekton_start prompt: "/<name> <arguments>".'
    ),
)
FIND: Final = MCPTool(
    name="tekton_find",
    title="Find Claude Code sessions",
    description=(
        "Recorded sessions, newest first: id, title, project, branch, tag, last change. `project` narrows to one "
        "project (short name or path), `text` to titles, branches or tags that contain it. Next: tekton_read to see "
        "where one stopped, tekton_start with `session` to continue it."
    ),
)
READ: Final = MCPTool(
    name="tekton_read",
    title="Read where a session stopped",
    description=(
        "A session and its last `last` turns, oldest first: what the user asked, what Claude Code answered, which "
        "tools it called. `session`: its id, the first 8 characters of it, or its exact title. Read it before "
        "continuing a session with tekton_start."
    ),
)
UPDATE: Final = MCPTool(
    name="tekton_update",
    title="Rename or tag a session",
    description="Give a session a `title` and/or a `tag` (an empty tag clears it); returns the session.",
    read_only=False,
)
PEERS: Final = MCPTool(
    name="tekton_peers",
    title="List open Claude Code sessions",
    description="The sessions open in a terminal right now: name, kind, idle or busy. tekton_send reaches one.",
)
SEND: Final = MCPTool(
    name="tekton_send",
    title="Message an open session",
    description=(
        "Deliver `text` to an open session by its name (see tekton_peers); it reads it at its next step. Returns "
        "whether it was delivered, not what the session answers."
    ),
    read_only=False,
)

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    tool.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(handler)
    for tool, handler in (
        (ENG, router.eng),
        (START, router.start),
        (STATUS, router.status),
        (TASKS, router.tasks),
        (CANCEL, router.cancel),
        (CATALOG, router.catalog),
        (FIND, router.find),
        (READ, router.read),
        (UPDATE, router.update),
        (PEERS, router.peers),
        (SEND, router.send),
    )
)
