# e-organon — the tree it grows into

`●` exists today · `○` planned · `(c)` e-arkhetypo's common, materialized · everything else is organon's own.
One tool = four files that share its name: `services/<section>/<word>.py` (the workflow), a route in
`api/router/<section>.py`, its twin in `mcp/tools/<section>.py`, its models in `models/<section>.py` — and a golden.

```
e-organon/
├── src/
│   └── e_organon/                     the ONE package: everything the project runs hangs here
│   │   ├── main.py                    ● composition root: routers, MCP door, lifespan chain
│   │   ├── __main__.py                ● serve · admin
│   │   ├── settings/
│   │   │   ├── files.py               ● ORGANON_FILES__ROOTS — where a path may point
│   │   │   ├── artifacts.py           ○ store root, TTL, quota
│   │   │   └── gpu.py                 ○ the one GPU slot: allowed, memory ceiling
│   │   ├── api/
│   │   │   ├── stream.py              ● one route, two readings: SSE events or the batch answer
│   │   │   ├── lifespan/              ● infra · db · providers · engines · services · mcp · sealed
│   │   │   └── router/
│   │   │       ├── health.py · auth.py · user.py          ● (template)
│   │   │       ├── doc.py             ● /doc/convert           ○ inspect fill stamp signature sign merge split
│   │   │       │                                                 compress protect redact render compose ocr extract diff
│   │   │       ├── image.py           ○ convert cutout upscale detect depth redact ocr barcode meta hash diff trace render scan optimize signature
│   │   │       ├── audio.py           ○ convert clean normalize diarize separate fingerprint transcribe speak
│   │   │       ├── video.py           ○ convert cut frames scenes subtitle gif fetch
│   │   │       ├── text.py            ○ detect translate grammar redact keywords count diff readability
│   │   │       ├── data.py            ○ query convert schema chart select
│   │   │       ├── web.py             ○ read capture archive links search
│   │   │       ├── organon.py         ○ find · job · artifact (the meta-tools)
│   │   │       └── tekton.py          ○ eng · work · session · live · catalog (the #tekton bridge)
│   │   ├── mcp/
│   │   │   ├── registry.py · mount.py · instructions.py · refusals.py   ●
│   │   │   └── tools/                 ● health user doc   ○ one twin module per router above
│   │   ├── services/                  the tools: one ToolFlow per word
│   │   │   ├── flow.py                ● ToolFlow — events, run, failures as the last event
│   │   │   ├── files.py               ● AllowedFiles — paths resolved and kept under the roots
│   │   │   ├── doc/convert.py         ● ConvertDocService   ○ inspect.py fill.py stamp.py signature.py …
│   │   │   ├── image/                 ○ cutout.py (signature's step) convert.py upscale.py …
│   │   │   ├── audio/ video/ text/ data/ web/   ○
│   │   │   ├── organon/               ○ find.py job.py artifact.py
│   │   │   └── tekton/                ○ eng.py work.py session.py live.py catalog.py (ported from e_metaxy)
│   │   ├── models/                    ● flow.py error.py doc.py   ○ image.py audio.py … artifact.py job.py tekton.py
│   │   │
│   │   │   ── e-arkhetypo's common, materialized whole INSIDE the package (c) ──
│   │   ├── engines/                   ● (c) auth cache dispatch health telemetry
│   │   │                              ○ artifact.py (content-addressed store) · gpu.py (the slot) · coder.py (Claude Agent SDK)
│   │   ├── processors/                ● (c) doc.py (DocProcessor)
│   │   │                              ○ pdf.py · image.py · signature.py · scan.py · media.py · table.py · text.py
│   │   ├── ports/                     ● (c) 18: documents markdown pages ner embed rerank queue store llm …
│   │   │                              ○ pdf raster matting detect ocr speech office grammar translate pii media table browser search coder
│   │   ├── providers/
│   │   │   ├── drivers/               ● (c) documents/docling ner/gliner embed/tei rerank/tei queue/{pgqueuer,awa}
│   │   │   │                                database/psqlpy store/{redis,sqlite} http/wreq auth/postgres llm …
│   │   │   │                          ○ speech/evoice office/gotenberg grammar/languagetool browser/playwright
│   │   │   │                            search/searxng meta/exiftool coder/claude pii/presidio
│   │   │   └── adapters/              ● (c) markdown/anytomd pages/liteparse extract language/lingua cache watch telemetry
│   │   │                              ○ pdf/{pikepdf,pdfium,pyhanko} raster/vips vision/opencv inference/onnx
│   │   │                                table/duckdb media/ffmpeg render/{typst,pandoc,resvg} code/{zxing,vtracer}
│   │   ├── infra/                     ● (c) auth config mcp errors logger settings state …
│   │   └── ops/                       ● (c) compose crypto file hash image registry wrappers
├── tests/
│   ├── unit/                          ● mirror of src (185 tests, 100 % coverage)
│   ├── acceptance/                    ○ golden files per tool: input → expected output (hash or semantic)
│   ├── resources/                     ● mcp/surface.json …   ○ golden/<section>/<word>/ · hostile/ (bombs, JS PDFs, SVG refs)
│   └── benchmark/                     ● the app under load   ○ tokens at rest with 150 tools
├── docs/   organon-study.md · tree.md · bridge.md (the e_metaxy bridge, until ported)
└── compose.yml · Dockerfile · Makefile · tach.toml · pyproject.toml
```

Rough size once the sections are in: ~110 tools, ~45 ports, ~35 drivers, ~40 adapters, ~25 processors;
~4 files per tool plus a golden. The common half (`(c)`) is ~170 files today and only grows by reverse-distill.
