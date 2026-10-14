# e-metaxy — design

μεταξύ, *the in-between*: the daimonic carries the word between those who rule and those who make (Symposium 202e).
e-metaxy carries a task from a **polymath** harness (OpenHuman, Hermes — broad, nomos) to an **engineer** harness
(Claude Code today, OpenCode next — narrow, techne) and carries the result back.

## Contract

One MCP server over Streamable HTTP on loopback. A caller never waits on work: every long action returns an id at
once; the caller polls, or is called back when the work ends.

| tool | in | out | effect |
|---|---|---|---|
| `task_start` | `prompt`, `profile`, `cwd`, `session?`, `fork?`, `caller?` | `Task` (running) | runs `prompt` on the profile's coder; `session` resumes it, `fork` branches it |
| `task_status` | `task` | `Task` | point-in-time read, never blocks |
| `task_cancel` | `task` | `Task` | interrupts a running task; a finished one is returned unchanged |
| `task_list` | `state?`, `limit` | `list[Task]` | newest first |
| `session_list` | `coder?` | `list[Peer]` | the coder's live sessions: name, kind, idle/busy |
| `session_send` | `peer`, `text`, `coder?` | `Receipt` | delivers `text` to a running interactive session |
| `profile_list` | — | `list[Profile]` | what a caller may choose |

A skill or slash command is a prompt: `task_start(prompt="/research vLLM sleep mode", …)`.

## Domain

- `Task` — immutable value: id, coder, profile, prompt, cwd, `state`, coder `session`, `result`, `error`, `cost`,
  `caller`, timestamps. A change is a new value.
- `State` — `running → done | failed | cancelled`; the transition table is the only way to move. A task found
  `running` after a restart becomes `failed` (`interrupted`), its session kept so the caller can resume it.
- `Profile` — the nomos of the bridge, declared in YAML: coder, permission mode, allowed/denied tools, roots the
  `cwd` must live under, max turns, max budget, model. A caller picks a profile by name and never passes flags.
  `bypassPermissions` is refused at load.
- `Peer` — a live session of a coder: name, kind, status. `Receipt` — delivery verdict of `session_send`.

## Ports (logic) → adapters (edge)

| port | does | adapter v1 | next |
|---|---|---|---|
| `Coder` | `run(spec) → Outcome`, `peers()`, `send(peer, text)` | `ClaudeCoder` — Claude Agent SDK (`run`), a `claude mcp serve` child (`peers`, `send` via ListAgents/SendMessage) | `OpenCodeCoder` — `opencode serve` |
| `Notifier` | `notify(task)` on a terminal state | `OpenHumanNotifier` — `POST /rpc openhuman.webhooks_trigger_agent` | webhook, Hermes |
| `Ledger` | tasks by id, newest first | core `StorePort` (sqlite KV, msgspec bytes) | — |

`Bridge` (logic) owns the lifecycle: it starts each run inside one `TaskGroup` bounded by a semaphore, records
every transition in the ledger, interrupts on cancel, and notifies the caller when a task ends. It imports ports
only.

## Edges

- Loopback only: binds `127.0.0.1`, rejects a foreign `Host` (DNS rebinding), optional bearer token.
- Runs on the host as the user who logged in to Claude Code: the SDK inherits that login (no API key) and
  `~/.claude` (CLAUDE.md, skills, agents, hooks) through `setting_sources = ["user", "project"]`.
- Served by granian (Rust ASGI) from the official `mcp` SDK's Streamable HTTP app; systemd user unit.

## Not in v1

- Workflows (Claude's `Workflow` tool) — they live inside the session that launched them; needs a held
  `ClaudeSDKClient`. Gap, not faked.
- Interrupting an interactive session from outside — no mechanism exists.
- MCP `tasks` (2026-07-28 spec) — OpenHuman's client does not speak them; job id + poll + callback instead.
