# Catalog

How a client finds the tool it needs, and what the tool list costs it at rest.

## `organon/find`

`POST /organon/find {query, section?}` (MCP: `organon_find`) ranks the MCP registry's tools against a need. No model,
no embeddings: the query and each tool's text are lower-cased words (`[a-z0-9]+`), and for each query word a tool scores

| the word is in the tool's | score |
|---|---|
| name (`doc_merge`: `doc`, `merge`) | 4 |
| title | 2 |
| description | 1 |

each field counted once per word. The best five come back — name, description, JSON Schema of the arguments — ties
broken by name. A query with no word lists the section (or every tool) by name; `section` keeps the tools whose name
begins with it. Same query, same answer.

## Tokens at rest

What a client pays on connect is the `tools/list` payload. Measured as the JSON the MCP server builds
(`ListToolsResult`, by alias, no nulls), in bytes and in tokens with tiktoken `cl100k_base` — a proxy: no harness
tokenizes with exactly it. Reproduce: `make test TESTARGS="-m slow"` (`tests/benchmark/e_organon/test_catalog.py`,
2026-11-05).

| registry | tools | bytes | tokens | tokens / tool |
|---|---|---|---|---|
| public image (`CORE`) | 16 | 16 763 | 4 214 | 263 |
| everything on: bridge, OCR, signing (`ROUTES`) | 29 | 28 616 | 7 180 | 248 |
| `ROUTES` + 150 synthetic | 179 | 174 537 | 43 830 | 245 |

(2026-11-05, after `doc/compose`, `doc/ocr`, `doc/sign` and `organon/submit`; `CORE` is what every deployment serves, `doc_ocr` and `doc_sign` come only where `OCR_ENABLED` / `SIGN_P12` are set. After `image/cutout`, `doc/stamp`, `doc/signature` it was 5 669 tokens at 25 tools; at 22 tools, before them, the bridge registry was 4 167
tokens and 190 a tool.) The synthetic tools are the real ones' shapes (title, description, argument and answer schemas) cycled under new names,
so their size is as realistic as the real ones'. The largest are `doc_stamp` and `doc_signature` (their tagged `at` schema,
about 700 and 600 tokens) and `organon_job` (its answer's schema, 425).

## Decision: no per-section profiles

Per-section MCP profiles (`/mcp/<section>`) are not built. The real registry costs 7 180 tokens with everything on, 3.6 % of a 200 000-token
window; the tool list scales at about 248 tokens a tool, so a tenth of that window (20 000 tokens) is reached at about
81 tools — 2.8 times what organon serves. The 150-tool case (43 830 tokens, 21.9 %) is where a harness defers tool
definitions or a profile earns its keep; it is not the case today. The benchmark holds the real registry under an
8 000-token budget (it was 5 000 until the stamp tools' schema passed it; 7 180 now, with 820 to spare); the day it fails, profiles are asked again — with `organon/find` already in place as the way to reach
a tool a client has not listed. Not measured: how Hermes loads MCP tools.
