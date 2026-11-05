# Changelog

## [Unreleased]

### Added
- `doc/stamp` and `doc/signature` (`TODO_jobs` step 5): an image (PNG, transparency kept) or a text drawn on a PDF page
  `at` a form field, a text anchor (found by pdfium's text search, `occurrence`, `offset`, `width`) or a box — a tagged
  union in the request; `doc/signature` is `image/cutout` then `doc/stamp`, one stream (`cutout.*`, `stamp.*`). Ports:
  `PdfPort.stamp`, `RenderPort.find`; REST, MCP `doc_stamp`/`doc_signature`, job kinds. Visual only, not PAdES.
  Placement tested against the page's own `cm` matrix (field, anchor ± 3 pt, box). The stamp tools' schema took the
  tool list to 5 669 tokens with the bridge (25 tools, 2.8 % of 200 k): profiles still not needed, budget test now
  8 000. `make check`: 505 passed, coverage 100 %.
- `image/cutout` (`TODO_jobs` step 4): the ink of a photographed signature as a transparent PNG in the outbox
  (`POST /image/cutout`, MCP `image_cutout`, a job kind on the `image` queue, `ORGANON_SLOTS_IMAGE`). `CutoutPort` +
  `OpencvAdapter` (flat-field by closing, Sauvola, darkness gate, specks dropped; soft alpha); the photo's pixels are read
  from its header first and refused over `ORGANON_MAX_PIXELS` (40 MP). Bench (`docs/bench/cutout.md`, raw samples kept,
  60 synthetic test images, interleaved, paired BCa bootstrap): A F 0.909 / IoU 0.834 / 50 ms p50 against rembg ISNet
  F 0.816 / IoU 0.689 / 931 ms, A − C F +0.100 CI [0.075, 0.116] > 0.03 → OpenCV wins; synthetic data only. Image: +508 MB
  (1 862 → 2 371 MB; opencv-headless, scikit-image, scipy, numpy). `make check`: 470 passed, coverage 100 %.
- Job ownership and a closed queue setting (`TODO_jobs` follow-ups): a job records its caller's account (`owner`) and its
  tool input travels under one key (`input`), so no input field can meet the dispatch's own kwargs (`attempts`,
  `coalesce`, `_trace`); the dispatch engine is common and untouched. Another account's job is 404 on `GET /jobs/{id}`,
  `/events`, `DELETE` and `organon_job`/`organon_cancel` (existence not revealed); the admin reaches every job.
  `QUEUE_ENGINE` is `Literal[pgqueuer]`: `awa` has no row (it takes a DSN, not the queue's database), so it is a config
  error at load, not a KeyError mid-lifespan. `make check`: 451 passed, coverage 100 %.
- Catalog (`TODO_jobs` step 3): `organon/find {query, section?}` (REST and MCP `organon_find`) ranks the MCP registry's
  tools by name 4 / title 2 / description 1 over lower-cased words, five at most, ties by name — no model
  (`docs/catalog.md`). Tools at rest, measured (tiktoken cl100k_base as proxy): 11 tools 2 209 tokens, 22 with the
  bridge 4 167 (2.1 % of 200 k), +150 synthetic 32 683 — about 190 a tool. Verdict: no per-section MCP profiles (a
  tenth of 200 k comes at ~105 tools); a 5 000-token budget test guards it. `make check`: 440 passed, coverage 100 %.
- Jobs (`TODO_jobs` step 2): every tool but tekton's is a kind `<section>/<word>` on its section's queue
  (`ORGANON_SLOTS_DOC`, default 2). `Prefer: respond-async` (RFC 7240) on a tool route answers `202 {job, state}` with
  `Location: /jobs/{id}`; `GET /jobs/{id}`, `GET /jobs/{id}/events` (SSE, polled until settled: `step`…, then `done` or
  `failed`, the very events of the tool's own stream) and `DELETE /jobs/{id}`; MCP `organon_job` (`wait` up to 25 s) and
  `organon_cancel`. Evidence: `doc/convert` queued streams `resolve`, `read`, `done` and settles `completed` with the
  batch's answer — in tests (memory) and live on ParadeDB/pgqueuer (throwaway databases); `make check` 421 passed,
  coverage 100 %. Fix to step 1: the queue's database is asyncpg — psqlpy cannot decode `name[]`, which pgqueuer's
  catalog queries return, so the durable queue never opened on it (measured live: fell to memory).
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
- Flaky test fixed: `test_organon_another_accounts_job_is_unknown_the_admin_reads_it[organon_cancel]` hung once in a
  hundred runs under load. Cause (found by logging the tool's path): the in-process MCP client runs a tool on the test's
  loop while the dispatch and its jobs' `anyio.Event`s live on the REST client's loop, and `organon_cancel` awaits the
  job's end across the two — an event set on one loop does not wake a waiter on the other. The test now cancels a
  `settled` job (REST waits for its events first). 120 of 120 runs clean under 30 parallel processes; not a product
  bug — a remote MCP client runs on the server's own loop.
- One base (`TODO_jobs` step 1): redis is out of organon (provider, state, tests, `fakeredis`); the queue lives in
  ParadeDB — a second `PsqlpyDriver` on `QUEUE_DSN` (`organon_background`, created by `api/lifespan/db` beside
  `organon`), `PgqueuerDriver` on it, `DispatchEngine` over memory as fallback, entered by `api/lifespan/jobs`; `queue`
  is a provider in `/ready` (optional; asyncpg since step 2 — see Added). Defaults now name `organon` / `organon_background`. `make check`: 385 passed,
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
