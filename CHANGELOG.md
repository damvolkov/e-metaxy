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

### Removed
- The OpenHuman legacy (PR #33).
