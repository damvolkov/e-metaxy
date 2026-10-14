# TODO — handoff (2026-10-14)

State, decisions and what is left, for the instance that takes e-metaxy over. Design: `docs/design.md`.

## State

- **v1 built and deployed.** PR #1 (`feat/bridge`): Bridge + ClaudeCoder + OpenHumanNotifier + 7 MCP tools.
  `make check` clean, 75 unit tests at 100 % coverage, 3 live tests green (`make live`: run, resume, peers).
- **Running** as `e-metaxy.service` (systemd user unit, `ops/e-metaxy.service`) on `127.0.0.1:45190/mcp`, from this
  checkout. Env: `~/.config/e-metaxy/env` (0600: `METAXY_OPENHUMAN_TOKEN`, `METAXY_PROFILES`). Ledger:
  `~/.local/share/e-metaxy/ledger.db`. Restart after a change: `systemctl --user restart e-metaxy`.
- **Verified end to end:** a task started over HTTP ran on Claude Code (subscription login, `apiKeySource: none`;
  `~/.claude` loaded — it answered in Spanish from CLAUDE.md) and OpenHuman acknowledged the callback.
- **`direct` profile (2026-10-14), verified live through the gateway:** `bypassPermissions` end-to-end — the bridge
  runs Claude Code as if Damien worked in it directly (Write + Bash auto-approved, no prompts, no turn/budget
  limits, roots `~/` and `/tmp`); task returns at once, status polls, and a JSON-RPC sink received the
  `webhooks_trigger_agent` callback with the full task payload on completion. `make live` covers it.
- **OpenHuman POC (2026-10-14), round trip closed.** `make openhuman` rendered `e-metaxy` into the core's
  `mcp_client.servers` and restarted it (healthy). A web-chat turn drove the orchestrator → it auto-discovered
  `mcp_e_metaxy_profile_list/task_start`, called `task_start(profile=direct, caller=openhuman)` → Claude Code
  answered → `OPENHUMAN_NOTIFIED` → the real core triaged the callback. Coders' children now see nvm's `node`
  (unit `Environment=PATH`): `~/.claude` hooks run inside gateway-launched sessions.
- **Actionable callback (2026-10-14).** OpenHuman's triage classifier reads only the trigger **payload** and label
  (never the `reason`), so the order and outcome ride in the payload. With that, triage decided `react →
  trigger_reactor` on a real sky-color task — the callback is now acted on, not merely filed. `session_history`
  and the `mcp` SDK's logs → structlog (`quiet()`, before the server is built) also landed; 100 % coverage holds.

## Decisions (do not relitigate without new evidence)

- **Python, not Rust:** the Claude Agent SDK exists only in Python/TS; its CLI control protocol changes weekly.
  Rust-backed where it counts: granian, pydantic-core, msgspec, wreq.
- **Official `mcp` v2 SDK** (`MCPServer`, explicit `add_tool`, Streamable HTTP app). Rust-backed Python MCP
  frameworks (nbmcp, chuk-mcp-rs) are immature; IBM deprecated its Rust MCP sidecar (2026-06).
- **Subscription login:** `ANTHROPIC_API_KEY` is blanked for the coder child (`CHILD_ENV`).
- **No bearer token in v1:** OpenHuman's MCP client sends no headers; loopback + Host check are the boundary.
  `METAXY_TOKEN` + `TokenGuard` exist for callers that can send one.
- **Job id + poll + callback**, not MCP `tasks`: OpenHuman's client (tinymcp) reads one SSE frame, no tasks.
- **Core materialized** from `../e-templates/systems/core` (`feat/darts-engine`, subset — see EXCLUDES in
  `scripts/materialize.py`); ty skips the copies (checked at source).

## Next

1. **OpenCode coder** — deferred by Damien (2026-10-14) until the Claude path is finished: no
   `adapters/coder/opencode.py` behind `CoderPort` (`opencode serve` HTTP API: sessions, prompt, abort) yet.
   Verify its API first; add `opencode` profiles; nothing else changes.
2. **OpenHuman acting on callbacks** — gateway side is done: the payload carries an instruction and triage now
   decides `react → trigger_reactor` on real tasks. What is left is on OpenHuman's side, not the bridge: its
   `trigger_reactor` tool-pack has **no Discord send** (it re-escalates to the orchestrator), and outbound
   Discord needs its bot token + a default `channel_id` bound in the channel config. Fix in e-engineer / OH
   config, then the result lands in a channel unattended.
3. **Workflows** (Claude `Workflow` tool) — need a held `ClaudeSDKClient` per task so the background workflow's
   notifications land in a live session. Not faked in v1.
4. **Bearer token end to end** — teach the transpiler to render `headers` for OpenHuman servers (Hermes already
   does), then set `METAXY_TOKEN`.
5. **Unified logs** — the `mcp` SDK logs through `rich`; route it into structlog (prod JSON).
6. **`session_list` for closed sessions** — the SDK has `list_sessions`/`get_session_messages`; expose them so a
   caller can pick a session to resume without knowing its id.
7. **MCP project template** — derive an e-templates `systems/mcp` from this repo (Damien: "eso ya lo vemos").

## Gotchas

- The in-memory MCP `Client` opens anyio scopes that must close in their own task: test fixtures hand out a
  context factory (`connect`), never a yielded client.
- `mcp` v2 surfaces a tool's message only for `ToolError`; `BridgeTools._common_plain` converts `MetaxyError`.
- `CallToolResult.is_error` (snake_case in v2), not `isError`.
- `webhooks_trigger_agent` blocks until OpenHuman's LLM triage ends (~25 s): `METAXY_OPENHUMAN_TIMEOUT` 5 min.
- granian imports the factory in its worker: the logger is configured in `assemble`, not in `__main__`.
- `pytest -m` on the CLI replaces the default `-m "not live"`: CI runs `-m "not slow and not live"`.
- CLI 2.1.296 accepts `--permission-mode bypassPermissions` alone — the SDK passes it through and no
  `--dangerously-skip-permissions` flag is needed; deny rules and hooks still hold inside the mode.
- `make openhuman` from an agent shell: the transpiler's `apply` is a guard_human command — needs
  `OPS_GLOBAL__HUMAN=1` (mandate) and `--yes` on the apply, or it asks for a terminal and aborts.
- OpenHuman connects MCP servers lazily (`expose = "deferred"`, supervisor tick 60 s): `connected=0 failed=0`
  at core startup is normal; the tools appear when a turn uses them.
- The unit's `Environment=PATH` pins `~/.nvm/versions/node/v24.14.0/bin` — when the nvm version changes, update it.
- OpenHuman's triage classifier is an LLM that reads only the trigger **payload** + label, never the `reason` field;
  it flips `acknowledge`/`react` run to run. To be acted on, the order and outcome must be inside the payload.
- `mcp` v2's `Client(...)` takes the URL string directly (`Client("http://127.0.0.1:45190/mcp")`); a single-object
  tool answer is the `structured_content` itself, only lists come wrapped in `{"result": …}`.
