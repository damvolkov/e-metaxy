# Bench: the raster library for `image/convert` and `image/optimize`

Decision record for the image section (2026-11-06). Scripts verbatim as they ran, kept as text so the linters leave them be:
[`image/`](image/) (`work.py.txt` one measurement in a fresh process, `run.py.txt` the interleaved runner, `analyse.py.txt`),
raw samples in `convert.jsonl`.

## Hypothesis (pre-registered, before any run)

libvips (`pyvips` 3.2.0 over `pyvips-binary` 8.18.7) converts and resizes faster and in less memory than Pillow 13.0.0 —
the library already in the image — at the same output size for the same nominal quality.

- Primary metric: wall time of decode + resize to fit 1600 px + encode, one measurement per fresh process; per cell
  (task, image) the ratio of medians vips / Pillow; the statistic is the geometric mean of the ratios over cells,
  **BCa bootstrap** 95 % (20 000 resamples of the cells).
- Secondary: peak RSS (`VmHWM`) of the process, the encoded size, SSIM against a Pillow Lanczos reference.
- Adopt vips only if (a) the upper bound of the time ratio is below **0.8** (at least 20 % faster, 95 %), (b) its peak RSS
  is not above Pillow's by more than 25 % in the median cell, (c) its output is within +-5 % of Pillow's size at SSIM within
  0.01, and (d) it ships wheels for cp314 and abi3 on linux x86_64 and macOS arm64. Anything less: Pillow stays — one
  dependency fewer, and the house reach order sends a tie to the one already in.

## Arms

| arm | what |
|---|---|
| **P** | Pillow 13.0.0: `Image.open`, `thumbnail` (JPEG draft + reducing gap, Lanczos), `exif_transpose`, `save` |
| **V** | pyvips 3.2.0 + pyvips-binary 8.18.7 (libvips 8.18): `thumbnail_buffer` (shrink-on-load, autorotate), `write_to_buffer`, default threads |
| **V1** | the same with `VIPS_CONCURRENCY=1`, to tell the library from its threads |

Python 3.14.3, Intel Core i9-14900K (32 threads), 188 GB, Linux. Each arm in its own virtualenv under `/tmp/bench-image`.

## Convert: results (2026-11-06; 15 cells, 7 measured rounds after 1 warm-up, 315 measurements per arm set)

Cells: JPEG, PNG and WebP photographs from the distribution's wallpapers (3.8 to 56 megapixels), to JPEG q85, WebP q80,
PNG (level 6) and AVIF q50, resized to fit 1600 px or whole. Medians per cell; full table in [`image/convert.md`](image/convert.md)
(`analyse.py.txt`'s output).

| | V (vips, threads) | V1 (vips, 1 thread) |
|---|---|---|
| time / Pillow, geometric mean over cells | **0.567**, 95 % BCa [0.427, 0.730] | 0.598, [0.381, 1.131] |
| faster than Pillow in | 14 of 15 cells | 12 of 15 |

Peak RSS, vips / Pillow, median cell: **1.63**. Encoded size, median 1.00 (JPEG, WebP, AVIF within 1 %; vips' default PNG
is 17 to 54 % larger). SSIM against the Pillow reference: vips minus Pillow, median -0.0004 (worst -0.0015).

## Convert: verdict

**Keep Pillow.** vips is faster, with an interval that clears the 0.8 line (upper bound 0.730), and equal in size and SSIM
for the lossy codecs — but it fails two of the four conditions fixed before the run: its peak memory is 1.63 times Pillow's
(a 25 % ceiling was set; the import alone is 12.6 MB over Pillow's 18.0 MB, the rest is its pipeline's buffers and threads) and `pyvips` ships no wheel at all, only an
sdist (a cffi build at install; `pyvips-binary` carries the library as an abi3 wheel for linux x86_64 and macOS arm64, but
the binding itself is built). Pillow 13.0.0 is already a dependency, reads and writes JPEG, PNG, WebP, TIFF and AVIF out of
its cp314 wheels (`features.check` for `webp`, `avif`, `libtiff`, `jpg`: all true), and a tie on cost goes to the one
already in. Where vips wins big (PNG: 3 to 5 times faster) the work is a lossless re-encode that `image/optimize` does with
another tool anyway. The cost of this verdict is latency on very large JPEGs: Pillow's `draft` mode (JPEG shrink-on-load)
is used for resizes, which is what put it at 276 ms for 8 MP in this table.
