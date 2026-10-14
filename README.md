# e-metaxy

μεταξύ — *the in-between*. An MCP gateway that carries tasks from **polymath** harnesses (OpenHuman, Hermes) to
**engineer** harnesses (Claude Code today, OpenCode next) and carries the results back.

A caller never waits on work: `task_start` returns a task id at once; `task_status` reads it (or waits a bounded
time); a caller that names itself is called back when the task ends. Live interactive Claude Code sessions are
listed and messaged by name.

```
OpenHuman ──MCP (HTTP, loopback)──▶ e-metaxy ──Agent SDK──▶ Claude Code (your login, your ~/.claude)
    ▲                                  │  └──claude mcp serve──▶ live sessions (ListAgents · SendMessage)
    └──── /rpc webhooks_trigger_agent ─┘  when a task ends
```

## Tools

| tool | does |
|---|---|
| `task_start(prompt, profile, cwd, session?, fork?, caller?)` | runs the prompt on the profile's coder; `session` resumes, `fork` branches; returns at once |
| `task_status(task, wait?)` | the task now, or once it ends within `wait` seconds |
| `task_cancel(task)` | interrupts a running task |
| `task_list(state?, limit?)` | newest tasks first |
| `session_list(coder?)` | live interactive sessions: name, ref, idle/busy |
| `session_send(peer, text, coder?)` | delivers text to a live session's inbox |
| `profile_list()` | the profiles a task may run under |

A skill or slash command is a prompt: `task_start(prompt="/research vLLM sleep mode", profile="research", …)`.

## Profiles

`profiles.yaml` is the nomos of the bridge: a caller names a profile, never a flag. Each fixes the permission mode
(`default`, `dontAsk`, `acceptEdits`, `plan`, `auto`, and `bypassPermissions` — used by `direct`, which approves
everything as if you worked in Claude Code yourself; deny rules and hooks still hold), the allowed and denied tools,
the roots `cwd` must live under, and turn/budget limits. Your `~/.claude` loads on top of every profile.

## Run

```bash
make install        # materialize the e-templates core, sync, hooks
make check          # lint · ty · tach · validate · drift · tests
make live           # the real Claude Code login on this host (spends a little quota)
make run            # serve on 127.0.0.1:45190
make unit           # install + start the systemd user unit
```

Configuration is `METAXY_*` (see `.env.example`), read from `~/.config/e-metaxy/env` by the unit. The service runs
as the user logged in to Claude Code: no API key — an `ANTHROPIC_API_KEY` in the environment is blanked for the
coder so the subscription login is used.

Design and boundaries: [`docs/design.md`](docs/design.md).
