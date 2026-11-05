# Bench: composing a PDF from a template and data

Decision record for `doc/compose` (2026-11-05). Raw data, scripts and the pre-registration are in [`compose/`](compose/):
`prereg.txt` (written before the run), `gen.py.txt` (the invoices), `invoice.typ.txt` (the typst template), `typst_arm.py.txt`,
`weasy_arm.py.txt` (the arms, the invoice as HTML/CSS), `run.py.txt` (interleaved runner and checks), `analyse.py.txt`,
`analysis.txt` (its output), `run.tsv` (`invoice, arm, ms, bytes, pages, text ok, PDF/A declared`) and `determinism.tsv` —
scripts verbatim as they ran, kept as text so the linters leave them be.

## Hypothesis

typst (a Rust binding on PyPI) renders a multi-page invoice faster than WeasyPrint (Python over pango), writes PDF/A-2b and
byte-deterministic output, and costs a smaller image. **Primary metric**: render latency per invoice, as the paired
log-ratio `log(ms_typst / ms_weasy)`, BCa 95 % (20 000 resamples). **Gates, all four, fixed beforehand**: (1) the interval's
upper bound is below 0 (typst faster); (2) typst's PDF declares PDF/A-2b (XMP `pdfaid:part` 2 and an output intent) on every
invoice; (3) the same invoice rendered twice gives the same bytes; (4) every item reference, the total and the number are in
the extracted text. If typst fails any, WeasyPrint takes the place if it passes (2)-(4). Secondary: p50/p95, PDF size, weight.

## Arms

| arm | what | versions |
|---|---|---|
| **TY** | `typst.compile` over the template's bytes, data as `sys_inputs`, `pdf_standards="a-2b"`, fixed `timestamp`, `ignore_system_fonts` (the fonts typst embeds only) | typst 0.15.0 (the one the project locks: 0.15.2 is under the 7-day freshness window; a first run on 0.15.2 gave 20.1 ms p50 and 7.6 x) |
| **WP** | `HTML(string=...).write_pdf(pdf_variant="pdf/a-2b", pdf_identifier=...)`, the same invoice in HTML/CSS, fixed `dcterms` dates | weasyprint 70.0 (pydyf 0.13.0, fonttools 4.68.0), pango from the host |

Python 3.14, Intel Core i9-14900K. Each arm in its own virtualenv, a worker process fed the same JSON paths. 60 invoices
(55-75 line items, Spanish text with accents, seed 1), **interleaved** in rotating order, 3 warm-ups discarded.

## Results (60 invoices)

| arm | ms p50 | ms p95 | PDF bytes (median) | text check | PDF/A-2b declared | same bytes twice (10) |
|---|---|---|---|---|---|---|
| **TY** typst | **21.3** | **32.0** | 95 066 | 60 / 60 | 60 / 60 | 10 / 10 |
| WP WeasyPrint | 156.4 | 205.1 | **27 566** | 60 / 60 | 60 / 60 | 10 / 10 |

`log(ms_TY / ms_WP)`: mean -1.969, 95 % CI **[-2.001, -1.934]**: typst is **7.2 x faster** (CI 6.9-7.4 x), on 60 of 60 invoices.
The two lay the same content on the same number of pages on 40 of the 60 (the page breaks differ by a line elsewhere; both
are right).

Weight, not part of the gates (virtualenv sizes; Docker was down, no image was built): the `typst` wheel is **81 MB** (the
compiler and its embedded fonts); WeasyPrint with its Python dependencies about **45 MB**, plus what the slim image lacks:
pango, harfbuzz, fribidi, fontconfig, glib and friends, about **8 MB** of Debian packages (host sizes of
`libpango`, `libpangoft2`, `libharfbuzz0b`, `libharfbuzz-subset0`, `libfribidi0`, `libfontconfig1`, `libglib2.0-0`, `libthai0`,
`libdatrie1`, `libgraphite2`), and a font package for it to draw with. typst is about 25-30 MB heavier; its PDF is 3.4 x
larger (it embeds whole fonts).

## Verdict

**Adopt typst.** Gates (1)-(4) all pass: 7.2 x faster, PDF/A-2b declared, deterministic, faithful text. WeasyPrint passed
(2)-(4) too, so the decision is the latency — 21 ms against 156 ms — and no system libraries in the image; the hypothesis'
"smaller image" is **false**: typst weighs about 25-30 MB more. It is what `providers/adapters/compose/typst.py` runs.

## Limits

- **PDF/A is declared, not validated**: veraPDF is not available here. The XMP and the output intent are in both PDFs; full
  conformance is unproven for either.
- One template shape (an invoice: a header, a table that spans pages, totals) — no images, no custom fonts, no forms.
  typst's embedded fonts only (`ignore_system_fonts`): a template that names another font falls back to them.
- The HTML/CSS arm is the author's: a more careful stylesheet might change WeasyPrint's time a little, not an order of
  magnitude.
- Latency is the render call alone, warm; the first call of a process is slower for both (typst 17 ms, WeasyPrint 170 ms
  in the probe).
- A typst template may import a package (`@preview/...`), which typst fetches from its registry on first use: a template is
  code, and trusted as such.
