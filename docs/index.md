# e-organon

ὄργανον, *the instrument*: canonical deterministic tools for agents — REST, streaming and MCP over workflows. No model
inside: the engines do the work. Study and plan: [the study](organon-study.md) · [the tree](tree.md).

## Quickstart

```bash
make check      # lint + types + architecture + tests
make run        # granian on APP_PORT (45190)
make docs       # serve this site at http://localhost:8000
make up         # docker compose up
```

## A tool

`section/word` — `doc/convert`, `doc/fill` — is a `ToolFlow` (`services/<section>/<word>.py`): a stream of `step`
events ending in `done` or `failed`. One `POST /<section>/<word>` streams it (`Accept: text/event-stream`) or answers
in batch; its MCP twin `<section>_<word>` is the same handler. Paths stay under `ORGANON_ROOTS`; written files land in
`ORGANON_OUTBOX`, named by content.

## Layout

Everything lives in one package, `src/e_organon/`, layered by [tach](https://tach.dev): `api/` and `mcp/` are the
doors, `services/` the tools, `models/` what crosses them; `engines/`, `processors/`, `ports/`, `providers/`, `infra/`
and `ops/` hold e-arkhetypo's common, materialized, beside organon's own.

| Module | Layer | Purpose |
|---|---|---|
| [`e_organon.main`](reference/e_organon/main.md) | api | Composition root: explicit registration only, `create_app` for granian |
| [`e_organon.api.stream`](reference/e_organon/api/stream.md) | api | One route, two readings: the events as SSE, or the answer |
| [`e_organon.api.router.doc`](reference/e_organon/api/router/doc.md) | api | The doc/ section's routes |
| [`e_organon.mcp.tools.doc`](reference/e_organon/mcp/tools/doc.md) | mcp | The doc/ section as MCP tools |
| [`e_organon.services.flow`](reference/e_organon/services/flow.md) | services | `ToolFlow`: the shape of every tool |
| [`e_organon.services.doc.convert`](reference/e_organon/services/doc/convert.md) | services | doc/convert |
| [`e_organon.engines.artifact`](reference/e_organon/engines/artifact.md) | engines | The outbox: outputs kept by content |
| [`e_organon.ports.pdf`](reference/e_organon/ports/pdf.md) | ports | A PDF's structure: read, merge, split, fill |
| [`e_organon.providers.adapters.pdf.pikepdf`](reference/e_organon/providers/adapters/pdf/pikepdf.md) | providers | pikepdf (qpdf) |
| [`e_organon.infra.config.services`](reference/e_organon/infra/config/services.md) | infra | Organon's own settings cluster |

Reference pages are generated from the sources: a new module under `src/` appears on the next build.
