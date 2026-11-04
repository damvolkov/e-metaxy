# e-organon

ὄργανον, *the instrument*. A hub of canonical deterministic tools — REST, streaming and MCP — for Claude Code, Hermes
and OpenCode: what costs an agent tokens or never gets done, done by code and small local models, never an LLM.

##### TOOLS #####

A tool is `section/word` — `doc/convert`, `doc/signature`, `image/cutout` — and inside it is a workflow over ports:
`services/<section>/<word>.py`, a `ToolFlow` whose events (`step` … `done` | `failed`) are the tool's whole life.
Every tool is one `POST /<section>/<word>`: `Accept: text/event-stream` streams the events, anything else gets the
answer; its MCP twin (`<section>_<word>`, same handler) answers in batch. Files travel by path under the allowed roots
(`ORGANON_ROOTS`: the vault, the workspaces), never as bytes in the arguments.

| Tool | Does | Engines |
|---|---|---|
| `doc/convert` | any document → Markdown | liteparse, docling-serve (when `DOCLING_URL`), anytomd |

Plan and study: `docs/organon-study.md`; the tree it grows into: `docs/tree.md`.

##### LAYOUT #####

```
src/e_organon/       # the service: api/ (lifespan, routers, stream), mcp/ (the MCP door), services/ (the tools), models/,
                     # and e-arkhetypo's common materialized whole inside it: engines/ infra/ ops/ ports/ processors/ providers/
tests/unit/      # mirrors src, import-mode=importlib; no service in the default run (`tests/conftest.py` fakes them all)
tests/benchmark/  # the load no single module owns: the whole app under concurrent traffic (`make stress`)
tests/support/   # the fakes the mirror shares (a scripted psqlpy pool, the accounts' store, the MCP client) — redis rides fakeredis
Dockerfile       # two-stage: builder (uv) + deploy (python-slim, non-root)
compose.yml      # single e-organon service, host network, :45190
```

##### TAXONOMY #####

Providers sit by capability — `e_organon/providers/<drivers|adapters>/<capability>/<name>.py`
(`e_organon.providers.drivers.store.redis`, `e_organon.providers.drivers.http.wreq`) — and the settings mirror that tree:
`st.providers.drivers.store.redis.url`, `st.app.port`. Every exception descends from `infra.errors.CoreError`; the
service's own live in `e_organon` and stay out of that tree. Env variable names are unchanged (`REDIS_URL`, `POSTGRES_DSN`).

##### USAGE #####

```bash
make install        # materialize infra + sync deps
make run            # python -m e_organon
make check          # lint + type + arch + validate + infra-drift + test
make integration    # the tests marked `integration` (a real service); out of check, test and cov
make stress         # soak concurrent-load tests
make up             # docker compose up
```

##### AUTH #####

`TokenMiddleware` resolves the `Authorization: Bearer <key>` header once per request into a caller (an account, the admin, or nobody); every route declares its access (`opt=OPT[Access.USER]`) and one guard admits the caller or refuses it. Keys are opaque, kept as a digest in Postgres (`providers/drivers/auth/postgres`), handed out once by the admin (`POST /auth/accounts/{name}/token`); the admin's first comes from `AUTH_SECRET=… python -m e_organon admin`.

The MCP door (`src/e_organon/mcp/`) serves the same resources to agents at `/mcp` under the same keys and the same refusals: each tool a Litestar route, twin of `api/router/<resource>.py`, reached through the official SDK by one engine (`infra/mcp`).

`make` alone lists every target.
