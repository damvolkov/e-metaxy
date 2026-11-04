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

### Removed
- The OpenHuman legacy (PR #33).
