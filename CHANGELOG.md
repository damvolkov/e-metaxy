# Changelog

## [Unreleased]

### Security
- **`doc/compose` is a sandbox** (TODO_doc follow-up): each compile runs in its own process with a dead proxy, no `HOME` and a 2 GiB
  address-space ceiling, stopped after `COMPOSE_TIMEOUT` (default 5 s) from outside — a thread cannot be killed — and its PDF held to
  `ORGANON_MAX_PAGES`. The binding cannot disable package downloads: a literal `"@ns/name"` is refused before compiling, one
  built at run time fails to connect. Reads stay in the template's folder (`/etc/passwd`, `../`: refused, tested). Cost: p50 16 ms
  in-process, 45 ms sandboxed on the golden invoice (`docs/bench/compose.md`). Tests: a long loop cut at the timeout with a clean
  `Failed` and the next compose fine, packages refused (static and built), reads refused, memory ceiling clean, page budget.

### Added
- **`lines` on `image/cutout`, `doc/signature` and `doc/sign`**: default on; off keeps every stroke (the pre-line arm), for a signature
  with its own straight underline (the −0.143 F loss of the form-lines bench). Tested on both settings at the adapter and through
  the three services; one clause in each tool description. Catalog 7 180 tokens with everything on, under the 8 000 budget.

### Added
- **`doc/ocr` (TODO_doc, 3)**: the words of a scanned PDF or an image, each with its box in points on the displayed page
  (origin bottom-left, as `doc/stamp`), and each page's text. Behind `OcrPort`; adapter `RapidocrAdapter` (PP-OCRv5 mobile
  detector + `latin` recogniser, onnxruntime). Off unless `OCR_ENABLED` (no route, no MCP tool, no models); on, models
  are fetched into `<ORGANON_DATA>/doc/models/rapidocr` at start. Pixel budget checked before decoding, page budget by the
  render port. Benched pre-registered against Tesseract (liteparse), 120 synthetic ES/EN pages, interleaved, paired BCa
  (`docs/bench/ocr.md`): CER 0.299 -> 0.030, `CER_T - CER_r5` +0.269 [+0.193, +0.353], p95 4.1 s; Tesseract is better on
  clean and lightly noisy pages (0.005 against 0.04) and collapses on bad scans. Adds rapidocr + onnxruntime (~120 MB in a
  venv; docker image delta not measured, the daemon was down).

- **`doc/sign` (TODO_doc, 4)**: a PDF signed in PAdES (`ETSI.CAdES.detached`, SHA-256, incremental, signable again) with
  pyHanko 0.38, the key a PKCS#12 named by `SIGN_P12` + `SIGN_P12_PASSWORD` (a secret) and an optional `SIGN_TSA_URL`
  (B-T). Without `SIGN_P12` there is no route, no MCP tool and no key read. Invisible by default; with `at` and one of
  `image`, `text` or `photo` the appearance is drawn first by `doc/stamp` / `doc/signature` and the signature seals it.
  Behind `SignPort`; adapter `PyhankoAdapter`. Evidence: tests mint a throwaway CA and PKCS#12 with `cryptography`; the
  signed PDF validates with pyHanko's own validator (intact, valid, trusted under the CA), a one-byte change after signing
  breaks it, a signed PDF takes a second signature. Not byte-deterministic by nature (the signature carries its time).
  Adds pyhanko, aiohttp and friends (~18 MB in a venv; docker image delta not measured, the daemon was down). No bench: pyHanko has no serious OSS rival in Python (endesive is the contrast, unmeasured) — the plan's own reasoning.

- **`doc/compose` (TODO_doc, 5)**: a typst template and JSON data composed into a PDF/A-2b through the outbox — `template`
  a name (`<ORGANON_DATA>/doc/templates/<name>.typ`, then the shipped ones: `invoice` ships in `src/e_organon/templates`) or a
  path under the roots; the template reads its own folder and nothing else. Byte-deterministic: fixed creation time, only
  typst's embedded fonts, sorted data; the same input is the same outbox file. Behind `ComposePort`; adapter `TypstAdapter`.
  Benched pre-registered against WeasyPrint on 60 two-to-three-page invoices, interleaved, paired BCa (`docs/bench/compose.md`):
  typst 21 ms p50 against 156 ms, log-ratio -1.969 [-2.001, -1.934] (7.2 x faster, 60/60), both declare PDF/A-2b and are
  deterministic; typst weighs about 25-30 MB more (81 MB wheel against ~45 MB + ~8 MB of Debian libraries), so the "lighter
  image" half of the hypothesis is false. PDF/A conformance not validated (no veraPDF). Golden: the invoice's text over
  `tests/resources/golden/invoice.json`. Catalog re-measured: 7 047 tokens with everything on, under the 8 000 budget.

### Changed
- **`image/cutout` drops printed form lines (TODO_doc, 2)**: long straight runs of the ink mask (probabilistic Hough, tilt
  allowed) are taken off, and a stroke crossing one is bridged. Benched pre-registered, A against A + lines, paired BCa on
  60 test images (`docs/bench/cutout.md`, "Form lines"): lined photos F 0.686 -> 0.929 (+0.236, CI [+0.214, +0.259], 60/60),
  line-free photos identical (0.953), +5 ms. Adapter = bench arm, mask IoU 1.0 on 220 images. Known loss, measured and
  not hidden: a signature with a 300-600 px straight underline loses it (F -0.143).

### Added
- **`organon/submit` (TODO_doc, 1)**: REST `POST /organon/submit` (202, `Location: /jobs/{id}`) and MCP `organon_submit`
  queue any doc/ or image/ tool by `<section>/<word>` with an `input` checked by `msgspec.convert` into the tool's own
  Struct; a tool that is no job (tekton, organon) or input that misses the Struct is a 422 before anything is queued.
  Reuses `JobsService.submit` (`enqueue` only resolves and decodes). Evidence: an MCP client submits `doc/convert` and
  polls `organon_job` to `completed`; 685 tests, coverage 100 %.

### Fixed
- **PDF outputs are deterministic**: pikepdf drew a random `/ID` and random resource names (`prefix="Org"`), so one
  request wrote a new file each run and the content-addressed outbox never deduplicated (found live: the same
  `doc/signature` gave three hashes). `deterministic_id=True` and the first `/Org<n>` free across every resource kind
  (pikepdf replaces a name across kinds). A test holds two stamps of one input byte-identical.

### TODO_jobs — finished (2026-11-05)
- One base (ParadeDB: pgqueuer queue, no redis), jobs for every doc/ and image/ tool, `organon/find`, `image/cutout`
  (benched), `doc/stamp`, `doc/signature`, the hostile corpus and goldens; v0.8.1 released and deployed. Live on the
  host: `doc/signature` by anchor in batch (125 ms), SSE (8 steps) and as a pgqueuer job (`/jobs/1`, completed);
  `/ready` all providers up.

### Fixed
- **The image ran Python 3.15 over a 3.14 venv** (Renovate bumped the deploy stage and `.python-version` alone): the
  published v0.8.0 `latest` could not `import e_organon`. Back to 3.14; the deploy stage now runs
  `python -c "import e_organon"` so such an image fails its build; Renovate keeps Python `<3.15` until lingua ships a
  3.15 wheel.
- **The sdist could not build**: the hostile corpus committed `escape`, an absolute symlink to `/etc/passwd`, which uv
  refuses in an archive. The fixture makes the link at test time; nothing absolute is committed.

### Added
- Quality (`TODO_jobs` step 6): a hostile corpus (`tests/resources/hostile/`: pixel bombs, a bad-CRC PNG, a PDF with
  JavaScript, one of 20 000 pages, truncated and garbage files, a symlink out of the roots) run through every doc/ and
  image/ tool on the whole stack — always a clean 200 or 422, under 10 s (125 cases) — and goldens for the new tools
  (cutout IoU ≥ 0.99 against a stored mask; stamp's matrix and pdfium's rendered pixels; signature's ink in the stamp).
  Limits added where the corpus found none: `ORGANON_MAX_PAGES` (5 000; a merge of 20 000 pages took 52 s, render
  drew them all) in the pikepdf and pdfium adapters, and `ORGANON_MAX_PIXELS` on a stamp's image. `make check`: 674
  passed, coverage 100 %.
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
- `doc/stamp` honours the page's geometry: `/Rotate` (0/90/180/270, inherited too) and the crop box. `at.box` is in the page
  *as displayed* (origin at the visible page's bottom-left after the turn); a field's and an anchor's rectangles are the
  PDF's, user space, turned into displayed ones by `PageGeometry` (new, in `ports/pdf`, with `PdfPort.geometry`); the image
  is drawn upright on a turned page. Tested on what pdfium renders, not on the matrix: a box's quadrants' colours at their
  places and an anchor stamp centred on the text's ink, on 0/90/180/270, cropped, 90 + cropped, 270 + cropped. Red before
  (6 of 14 failed on the old code). `occurrence` counts in pdfium's reading order, which follows the displayed page.
  `make check`: 541 passed, coverage 100 %.
- `image/cutout` without scikit-image: Sauvola ported to `cv2.boxFilter` (float64, reflect-101 borders, R = 1.0 as
  scikit-image sets it for a float image), dropping scikit-image, scipy, imageio, tifffile and lazy-loader. Equivalence
  on the 80 bench images: ink masks identical (pixel IoU min 1.000000, median 1.000000), F median on test 0.9094 both
  ways (`docs/bench/cutout.md`, "Port"). Image: 2 371 → 2 161 MB (−210 MB; +299 MB over the
  1 862 MB before the image tools, all of it opencv-headless and numpy).
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
