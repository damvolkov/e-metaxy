# e-metaxy

<p align="center">
  <img src="assets/logo.svg" alt="e-metaxy" height="110" />
</p>

μεταξύ — *the in-between*. An MCP gateway that carries tasks from **polymath** harnesses (OpenHuman, Hermes) to
**engineer** harnesses (Claude Code today, OpenCode next) and carries the results back.

A caller never waits on work: `work_start` returns a task id at once; `work_status` reads it (or waits a bounded
time); a caller that names itself is called back when the task ends. Recorded sessions are found, read and
continued; live interactive sessions are listed and messaged by name.

```
OpenHuman ──MCP (HTTP, loopback, OAuth)──▶ e-metaxy ──Agent SDK──▶ Claude Code (your login, your ~/.claude)
    ▲                                         │  └──claude mcp serve──▶ live sessions (ListAgents · SendMessage)
    └──── /rpc webhooks_trigger_agent ────────┘  when a task ends
```

## Tools

| tool | scope | does |
|---|---|---|
| `eng(text, project?, profile?, caller?)` | work · sessions | the user's `eng` message as typed, in the grammar every front shares: `eng [project:] <order>` new · `eng @ref: <order>` continue · `eng @ref+: <order>` branch · `eng @ref?` read · `eng @ref = <title>` rename · `eng ls [project]` · `eng ps` · `eng stop <task>` |
| `work_start(prompt, project, profile?, session?, fork?, caller?)` | work | runs the prompt in Claude Code; `session` continues, `fork` branches; returns at once |
| `work_status(task, wait?)` | work | the task now, or once it ends within `wait` seconds (≤25) |
| `work_list(state?, limit?)` | work | newest tasks first |
| `work_cancel(task)` | work | interrupts a running task |
| `catalog(project?)` | work | the slash commands, skills and agents Claude Code offers in a project |
| `session_find(project?, text?, limit?)` | sessions | recorded sessions, newest first, filtered by title, branch or tag |
| `session_read(session, last?)` | sessions | a session and its last turns — where it stopped |
| `session_update(session, title?, tag?)` | sessions | renames or tags a session |
| `live_list()` | live | sessions open in a terminal: name, idle/busy |
| `live_send(peer, text)` | live | delivers text to an open session's inbox |

A skill or slash command is a prompt: `work_start(prompt="/research vLLM sleep mode", project="e-voice", …)`. A
project is a short name, resolved under `~/workspaces` (`METAXY_WORKSPACES`), or a path.

## Auth

OAuth 2.1 only, the way MCP clients expect it: e-metaxy is its own authorization server. A client registers
itself (dynamic registration, PKCE), the browser lands on `/oauth/consent`, and the owner approves it with a
passphrase. Access tokens are short JWTs bound to `/mcp`; refresh tokens rotate and can be revoked. `/ops` asks for
the same token.

```bash
uv run e-metaxy keys     # CRYPTO__SECRET='…'          — the key that signs the tokens
uv run e-metaxy owner    # METAXY_AUTH_OWNER_HASH='…'  — argon2 of the owner's passphrase (asked twice)
```

Both lines go to `~/.config/e-metaxy/env`; without an owner the service refuses to start.

## Profiles

`profiles.yaml` is the nomos of the bridge: a caller names a profile, never a flag. Each fixes the permission mode
(`default`, `dontAsk`, `acceptEdits`, `plan`, `auto`, and `bypassPermissions` — used by `direct`, which approves
everything as if you worked in Claude Code yourself; deny rules and hooks still hold), the allowed and denied tools,
the roots `cwd` must live under, and turn/budget limits. Your `~/.claude` loads on top of every profile.

## Run

```bash
make install        # materialize the e-arkhetypo core, sync, hooks
make check          # lint · ty · tach · validate · drift · tests
make live           # the real Claude Code login on this host (spends a little quota)
make run            # serve on 127.0.0.1:45190
make deploy         # build the image, install compose + systemd unit: permanent container service
make unit           # the same service host-native instead (uv, no docker)
make probe          # the live service as an MCP client: owner sign-in, list the tools
make probe TOOL=session_find INPUT='{"text":"voice"}'   # …or call one
```

The container runs Claude Code as you would at a terminal, with your setup mounted at the same paths: `~/.claude`
and `~/.claude.json`, `~/workspaces`, the toolchains (`~/.local/bin`, uv, the native claude, rust) and the ledger.
No ssh keys: git reaches GitHub over https with `GH_TOKEN`. `deploy/systemd/emetaxy.service` keeps it up through
boot and logout; images publish to `ghcr.io/damvolkov/e-metaxy` from the `release` workflow (manual dispatch).

Configuration is `METAXY_*`, `CRYPTO__SECRET` and `GH_TOKEN`, read from `~/.config/e-metaxy/env`. `make probe`
signs in with the passphrase in `~/.config/e-metaxy/passphrase` (`METAXY_PROBE_PASSPHRASE`). The service runs as
the user logged in to Claude Code: no API key — an `ANTHROPIC_API_KEY` in the environment is blanked for the coder
so the subscription login is used.

Design and boundaries: [`docs/design.md`](docs/design.md).
