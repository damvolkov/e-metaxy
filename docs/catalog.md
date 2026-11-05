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
| public image (`CORE`) | 11 | 9 093 | 2 209 | 201 |
| with the bridge (`ROUTES`) | 22 | 17 120 | 4 167 | 189 |
| `ROUTES` + 150 synthetic | 172 | 133 892 | 32 683 | 190 |

The synthetic tools are the real ones' shapes (title, description, argument and answer schemas) cycled under new names,
so their size is as realistic as the real ones'. The server's `instructions` add 382 tokens. The largest tool is
`organon_job` (425 tokens, its answer's schema), the median 165.

## Decision: no per-section profiles

Per-section MCP profiles (`/mcp/<section>`) are not built. The real registry costs 4 167 tokens, 2.1 % of a 200 000-token
window; the tool list scales at about 190 tokens a tool, so a tenth of that window (20 000 tokens) is reached at about
105 tools — five times what organon serves. The 150-tool case (32 683 tokens, 16 %) is where a harness defers tool
definitions or a profile earns its keep; it is not the case today. The benchmark holds the real registry under a
5 000-token budget; the day it fails, profiles are asked again — with `organon/find` already in place as the way to reach
a tool a client has not listed. Not measured: how Hermes loads MCP tools.
