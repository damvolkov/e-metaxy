# Bench: reading words with their boxes off a scanned page

Decision record for `doc/ocr` (2026-11-05). Raw samples, scripts and the pre-registration are in [`ocr/`](ocr/):
`prereg.txt` (written before the test run), `gen.py.txt` (the synthetic pages), `t.py.txt`, `rapid.py.txt` (the arms),
`run.py.txt` (the interleaved runner and the scorer), `analyse.py.txt`, `analysis.txt` (its output), `test.tsv` and `dev.tsv`
(one row per page and arm: `page, arm, lang, level, ms, CER, recall, exact, IoU`) — scripts verbatim as they ran, kept as
text so the linters leave them be.

## Hypothesis

RapidOCR (PP-OCR models on onnxruntime) reads scanned pages, Spanish and English, with a lower character error rate than
Tesseract, which already ships inside liteparse. **Primary metric: page CER**, paired per page, BCa bootstrap 95 %
(20 000 resamples) over the 120 test pages. **Decision rule, fixed beforehand**: adopt RapidOCR (the better of r5, r6 by mean
CER) if the lower bound of `CER_T - CER_R` is above **0.01** and its page p95 latency is under **10 s**; otherwise keep
Tesseract, which costs no new dependency.

## Arms

| arm | what | versions |
|---|---|---|
| **T** | Tesseract through liteparse (in process), `tessdata` `spa` / `eng` by the page's language, word boxes (`emit_word_boxes`) | liteparse 2.18.0 |
| **r5** | RapidOCR, PP-OCRv5 mobile detector + `latin` recogniser (one model for both languages), word boxes | rapidocr 3.10.0, onnxruntime 1.31.1 (CPU) |
| **r6** | RapidOCR defaults: the wheel's PP-OCRv6 small detector and recogniser, word boxes | idem |

Python 3.14. Machine: Intel Core i9-14900K, 32 threads, CPU only, `OMP_NUM_THREADS=4`. Each arm in its own virtualenv
(`env-tess`, `env-rapid`), a worker process fed the same page paths over stdin.

## Method

- Data (`gen.py.txt`): A4 pages at 150 dpi (1240 x 1754) with 7-10 sentences of known text, **Spanish and English**
  (accents, ñ, ü, numbers, addresses), three fonts of 24-30 px, word boxes known exactly. Three degradations: **clean**
  (JPEG 90), **noisy** (rotation +-1 degree, blur 0.8, Gaussian noise 10, JPEG 60), **bad** (rotation +-2.5 degrees, blur 1.3,
  a 0.6 x down-and-up scale, low contrast, uneven light, noise 18, JPEG 35). **120 test pages** (20 per language and level,
  seed 2), 18 dev pages (3 per language and level, seed 1: used only to settle the scorer).
- **Interleaved** runs, each page to every arm in a rotating order; 2 warm-up pages discarded.
- CER: Levenshtein distance over the words joined by a space, over the truth's length. Box metrics: a truth word is *found*
  when a predicted box has its centre inside the truth box grown by half its height vertically and a quarter horizontally
  (engines draw boxes of different tightness; a strict IoU scored the margin, not the reading — decided on dev), and
  *exact* when its text matches too. Latency is the recognition call alone, per page.

## Results (120 test pages)

| arm | CER mean | CER median | words found | words exact | ms p50 | ms p95 |
|---|---|---|---|---|---|---|
| T Tesseract (liteparse) | 0.299 | 0.010 | 0.705 | 0.696 | 723 | 1 467 |
| **r5** RapidOCR PP-OCRv5 latin | **0.030** | 0.001 | **0.971** | **0.961** | 2 076 | 4 059 |
| r6 RapidOCR PP-OCRv6 small | 0.042 | 0.004 | 0.968 | 0.930 | 1 999 | 3 392 |

`CER_T - CER_r5`: **+0.269, 95 % CI [+0.193, +0.353]**; `CER_T - CER_r6`: +0.257 [+0.180, +0.341]; `CER_r6 - CER_r5`:
+0.012 [-0.001, +0.026] (a tie overall; r5 is better on English, +0.022 [+0.004, +0.045]).

By level (mean CER, T / r5 / r6):

| level | T | r5 | r6 | note |
|---|---|---|---|---|
| clean | **0.006** | 0.045 | 0.050 | Tesseract better: `CER_T - CER_r5` -0.039 [-0.065, -0.021] |
| noisy | **0.005** | 0.036 | 0.062 | Tesseract better: -0.031 [-0.054, -0.015] |
| bad | 0.886 | **0.010** | 0.015 | Tesseract reads almost nothing (words found 0.12); +0.876 [+0.813, +0.918], r5 better on 40 of 40 |

By language: Spanish T 0.283 / r5 0.030; English T 0.315 / r5 0.030 — the same story.

## Verdict

**Adopt r5** (RapidOCR, PP-OCRv5 mobile detector, `latin` recogniser). The rule holds: the interval's lower bound
(+0.193) is far above 0.01 and the p95 is 4.1 s, under 10. The weight of the result is the degraded pages: Tesseract through
liteparse returns nothing usable on a tilted, soft, low-contrast scan, where RapidOCR still reads 99 % of the words. On
clean and lightly noisy pages Tesseract is the better reader (CER 0.005 against 0.04) and three times faster; the adapter
is the one engine, so that is the price. One `latin` model reads Spanish and English alike (the `language` argument is not
needed by the engine).

## Limits

- **Synthetic pages only**: rendered text from three Latin fonts, no handwriting, no tables, no stamps, no columns, no
  photographs of paper. A real scan has all of those; the scores rank the arms on a generator, not on a mailroom.
- **The Tesseract arm is liteparse's integration**, not a tuned `tesseract` (no page-segmentation modes, no preprocessing,
  liteparse's own confidence filter): the collapse on bad pages may owe to it. It is the Tesseract the service ships today,
  which is the comparison that counts for the decision, not a verdict on Tesseract.
- The corpus is 12 sentences per language, reshuffled: the recognisers see nothing a dictionary would not give them.
- CPU only (`OMP_NUM_THREADS=4`); latency scales with the page's text, not its pixels alone. A4 at 150 dpi.
- Box scoring is permissive on purpose (centre in the grown truth box); the reported "found" is not a localisation
  accuracy — the adapter's boxes are the engine's.
- Cost not measured by `docker build` (the daemon was down): the added packages weigh about 120 MB in a virtualenv
  (rapidocr 44 MB with its bundled v6 models, onnxruntime 63 MB, shapely, pyclipper, omegaconf and the rest about 12 MB), and the
  two v5 models and the angle classifier about 13 MB are fetched into `<data>/doc/models` once.
