# e-metaxy — design

μεταξύ, *the in-between*: the daimonic carries the word between those who rule and those who make (Symposium 202e).
e-metaxy carries a task from a **polymath** harness (OpenHuman, Hermes — broad, nomos) to an **engineer** harness
(Claude Code today, OpenCode next — narrow, techne) and carries the result back.

## Contract

One MCP server over Streamable HTTP on loopback. A caller never waits on work: every long action returns an id at
once; the caller polls, or is called back when the work ends.

| tool | scope | in | out | effect |
|---|---|---|---|---|
| `work_start` | work | `prompt`, `project`, `profile?`, `session?`, `fork?`, `caller?` | `Task` (running) | runs `prompt` in the profile's coder; `session` continues it, `fork` branches it |
| `work_status` | work | `task`, `wait?` | `Task` | the task now, or once it ends within `wait` (≤25 s) |
| `work_list` | work | `state?`, `limit` | `list[Task]` | newest first |
| `work_cancel` | work | `task` | `Task` | interrupts a running task; a finished one is returned unchanged |
| `catalog` | work | `project?` | `CoderCatalog` | slash commands, skills and agents the coder offers there — no model turn |
| `session_find` | sessions | `project?`, `text?`, `limit` | `list[CoderSession]` | recorded sessions, newest first, by title, branch or tag |
| `session_read` | sessions | `session`, `last` | `SessionRead` | the session and its last turns: user, assistant, tool |
| `session_update` | sessions | `session`, `title?`, `tag?` | `CoderSession` | renames or tags it |
| `live_list` | live | — | `list[Peer]` | the coder's open sessions: name, kind, idle/busy |
| `live_send` | live | `peer`, `text` | `Receipt` | delivers `text` to an open interactive session |

The profiles are listed in `work_start`'s own description. A skill or slash command is a prompt:
`work_start(prompt="/research vLLM sleep mode", project="e-voice")`. A project is a short name resolved under the
workspace root (`root/name`, `root/*/name`; ambiguous or unknown names are refused with the candidates) or a path.

## Domain

- `Task` — immutable value: id, coder, profile, prompt, cwd, `state`, coder `session`, `result`, `error`, `cost`,
  `caller`, timestamps. A change is a new value.
- `State` — `running → done | failed | cancelled`; the transition table is the only way to move. A task found
  `running` after a restart becomes `failed` (`interrupted`), its session kept so the caller can resume it.
- `Profile` — the nomos of the bridge, declared in YAML: coder, permission mode, allowed/denied tools, roots the
  `cwd` must live under, max turns, max budget, model. A caller picks a profile by name and never passes flags.
  `bypassPermissions` exists only as a profile a caller chooses by name (`direct`): full permission, as if working
  in Claude Code directly — deny rules and hooks still hold.
- `Peer` — a live session of a coder: name, kind, status. `Receipt` — delivery verdict of `session_send`.

## Ports (logic) → adapters (edge)

| port | does | adapter v1 | next |
|---|---|---|---|
| `Coder` | `run(spec) → Outcome`, `sessions`, `session`, `turns`, `update`, `catalog`, `peers()`, `send(peer, text)` | `ClaudeCoder` — Claude Agent SDK (`run`), a `claude mcp serve` child (`peers`, `send` via ListAgents/SendMessage) | `OpenCodeCoder` — `opencode serve` |
| `Notifier` | `notify(task)` on a terminal state | `OpenHumanAdapter` — `POST /rpc openhuman.webhooks_trigger_agent` | webhook, Hermes |
| `Ledger` | tasks by id, newest first; the authority's records | core `StorePort` (sqlite KV, msgspec bytes) | — |
| `Owner` | `admits(secret)` | `PassphraseAdapter` — argon2 hash checked by core `Crypto` | passkey |

`Bridge` (logic) owns the lifecycle: it starts each run inside one `TaskGroup` bounded by a semaphore, records
every transition in the ledger, interrupts on cancel, and notifies the caller when a task ends. It imports ports
only.

## Edges

- Loopback only: binds `127.0.0.1`, rejects a foreign `Host` (DNS rebinding).
- OAuth 2.1 only. `Authority` (logic) is the MCP SDK's authorization-server provider over the ledger, the owner
  port and core `Crypto`: dynamic client registration, PKCE, a consent page where the owner approves with a
  passphrase (attempts capped), single-use codes and rotating refresh tokens stored by SHA-256, access tokens as
  JWTs bound to the `/mcp` resource, revocation. Every tool checks its scope; `/ops` wants the same bearer.
- Runs on the host as the user who logged in to Claude Code: the SDK inherits that login (no API key) and
  `~/.claude` (CLAUDE.md, skills, agents, hooks) through `setting_sources = ["user", "project"]`.
- Served by granian (Rust ASGI) from the official `mcp` SDK's Streamable HTTP app; a compose service under a
  systemd user unit, the owner's setup mounted at the same paths.

## Not in v1

- Workflows (Claude's `Workflow` tool) — they live inside the session that launched them; needs a held
  `ClaudeSDKClient`. Gap, not faked.
- Interrupting an interactive session from outside — no mechanism exists.
- MCP `tasks` (2026-07-28 spec) — OpenHuman's client does not speak them; job id + poll + callback instead.
