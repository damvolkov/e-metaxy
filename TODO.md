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
- **Wiring:** e-engineer PR #40 declares `e-metaxy` in `core/nomos/config/mcp.yaml` + `stack.yaml` (kind `mcp`).
  After merge, `make openhuman` renders it into OpenHuman's `mcp_client.servers`.

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

1. **OpenCode coder** — `adapters/coder/opencode.py` behind `CoderPort` (`opencode serve` HTTP API: sessions,
   prompt, abort). Verify its API first; add `opencode` profiles; nothing else changes.
2. **OpenHuman acting on callbacks** — today its triage answers `ACKNOWLEDGE` (no action). Shape `reason`/`payload`
   so triage escalates (e.g. post the result to Discord), or adjust OpenHuman's triage policy in core.
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
