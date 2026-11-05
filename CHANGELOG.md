# Changelog

## [Unreleased]

### Added
- The skeleton (`TODO_skeleton`): `e_organon` on e-arkhetypo's api template with common materialized inside the
  package; the canonical tool shape — `POST /<section>/<word>`, SSE or batch by `Accept`, its MCP twin from the same
  handler; `doc/` with convert, inspect, fill, merge, split, render (docling + anytomd, pikepdf, pdfium) and the
  content-addressed outbox. `doc/convert` live: batch 36 ms, SSE 0.66 s on a 1.5 MB PDF.
- The #tekton bridge (`TODO_organon` step 5), ported from e_metaxy: coder port, Claude driver (Agent SDK +
  `claude mcp serve`), bridge engine, eleven `tekton/<word>` tools. Off unless `TEKTON_PROFILES` is set, so the public
  image starts without the Claude CLI. Organon keys by bearer header replace e_metaxy's OAuth authority.
- Data volume (`TODO_organon` step 6): `ORGANON_DATA` (`/data` in the image) holds a subtree per section and the
  store (`store/app.db`). doc/'s OCR models land in `doc/models/tessdata`, fetched at open when `DOC_OCR` is on and
  reused after: first start 2.5 s (eng+spa, 29 MB), second 0.25 s.

### Changed
- One base (`TODO_jobs` step 1): redis is out of organon (provider, state, tests, `fakeredis`); the queue lives in
  ParadeDB — a second `PsqlpyDriver` on `QUEUE_DSN` (`organon_background`, created by `api/lifespan/db` beside
  `organon`), `PgqueuerDriver` on it, `DispatchEngine` over memory as fallback, entered by `api/lifespan/jobs`; `queue`
  is a provider in `/ready` (optional). Defaults now name `organon` / `organon_background`. `make check`: 385 passed,
  coverage 100 %.
- Settings as category clusters (e-nous settings law, e-arkhetypo #109): `infra/config/{infra,providers,engines,
  processors,services,api,mcp,cli,…}.py` hold UPPERCASE typed fields named as their env variables; one `Settings`,
  `settings = Settings()`, read only by the composition root, which passes keyword arguments to every provider, engine,
  processor and service (`api/admin.mint` too). The tree composer and the per-scope config tree are gone; the root
  configures the logger with APP_ENV; liteparse keeps its OCR warm-up. Every env name of main held: 266 of 266
  (`tests/resources/settings/env.json`); gates in `tests/unit/e_organon/infra/test_settings.py`. `make ci`: 381
  passed, coverage 100 %.

### Removed
- The OpenHuman legacy (PR #33).
