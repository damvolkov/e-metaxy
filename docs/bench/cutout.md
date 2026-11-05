# Bench: cutting ink out of a photo

Decision record for `image/cutout` (2026-11-05). Raw samples, generator and arm scripts are in
[`cutout/`](cutout/): `gen.py.txt` (the synthetic photos), `base.py.txt`, `a.py.txt`, `c.py.txt` (the arms), `run.py.txt` (the
interleaved runner), `port.py.txt` (the equivalence check of the port below) — the scripts verbatim as they ran, kept as text so the linters leave them be —, `test.tsv` and `dev.tsv` (one row per image and arm: `image, arm, ms, F, IoU`).

## Hypothesis

A classical pipeline — flat-field the sheet, local threshold, drop specks — lifts the ink of a phone photo of a signature
at least as well as a segmentation network, at a fraction of the latency. The bench decides against rembg's ISNet; the
margin that counts is **0.03 F-measure**: arm A must beat the control by more than that, paired, at 95 %.

## Arms

| arm | what | versions |
|---|---|---|
| **A** | grey ÷ morphological closing (ellipse 31), Sauvola (window 25, k 0.2) AND flat < 150, connected components, specks < 30 px dropped | opencv-python-headless 5.0.0.93, scikit-image 0.26.0, numpy 2.5.4 |
| **C** | rembg `isnet-general-use`, its mask as the ink | rembg 2.0.86, onnxruntime 1.31.1 (CPU) |
| base | global Otsu on the luminance | opencv-python-headless 5.0.0.93 |

Python 3.14. Machine: Intel Core i9-14900K, 32 threads, CPU only, `OMP_NUM_THREADS=4`.

## Method

- Data: synthetic photos with an exact ink mask (strokes of varying width on tinted paper, uneven light, a soft shadow, a
  printed form line, slight perspective, blur, JPEG): **60 test images** (seed 2), **20 dev images** (seed 1). A's
  parameters were fixed on the dev set only.
- Arms ran in **separate virtualenvs**, each a worker process fed the same image paths.
- **Interleaved** runs: each image goes to every arm in a rotating order; **3 warm-up images discarded**.
- Metrics against the mask: F-measure (DIBCO's), IoU, latency of the cut alone (ms).
- Paired comparison: A − C per image on F, **BCa bootstrap** 95 % interval.

## Results (60 test images, medians)

| arm | F | IoU | ms p50 | ms p95 |
|---|---|---|---|---|
| **A** OpenCV + Sauvola | **0.909** | **0.834** | **50** | 119 |
| C rembg ISNet | 0.816 | 0.689 | 931 | 1 536 |
| base Otsu | 0.039 | 0.020 | 0.5 | 1.1 |

A − C on F: **+0.100**, 95 % CI **[0.075, 0.116]**; A wins on 54 of 60 images. ISNet's precision is 0.69: it fattens the
stroke, which is what costs it IoU. The interval clears the 0.03 threshold.

## Verdict

**Adopt A.** It is better by +0.100 F (CI above 0.03), 18× faster at the median, in-process, with no model to download.
It is what `providers/adapters/cutout/opencv.py` runs. The alpha channel (soft edges from the flattened darkness) is the
adapter's, not part of this bench.

## Port: scikit-image out (2026-11-05)

The adapter keeps arm A's method and drops its dependency: Sauvola's threshold is `cv2.boxFilter` on the grey and its
square (float64, `BORDER_REFLECT_101`, which is scikit-image's `reflect` padding), `T = m * (1 + k * (s / R - 1))` with
the window 25 and k 0.2. `R` is **1.0**, not 127.5: scikit-image sets it to half of the *dtype's* range, and for the float32
image the bench handed it that range is [-1, 1] whatever the pixel values (`threshold_sauvola` with `r=None`,
`dtype_limits`) — the bench's numbers are of that R, so the port keeps it. scikit-image, scipy, imageio, tifffile and
lazy-loader leave the image: 2 371 → 2 161 MB (`docker build`).

Equivalence, not a new bench: on the 80 bench images (20 dev, 60 test) the ink mask of the port against the skimage one
(`cutout/port.py.txt`):

| | pixel IoU old vs new | F median on test, against the exact masks |
|---|---|---|
| min / median over 80 images | 1.000000 / 1.000000 | skimage 0.9094, port 0.9094 |

The masks are identical on every image; the benchmarked 0.909 stands. The adapter's own test holds the formula against
`numpy`'s reflect padding on random data.

## Limits

- **Synthetic only.** No public dataset of signature photos with masks exists (DIBCO are scans); there are no real photos
  in the bench yet. The scores are a ranking of the arms on a generator, not a promise on a phone.
- The generator's **paper tint is unrealistically strong**, which favours any method that flattens the background.
- A **form line darker than the gate** (flat < 150) is ink to A: the generator draws one at 0.55 × the paper's grey,
  inside the gate; a lighter printed line falls outside it (the adapter's test uses 0.7 ×). Not measured separately.
- Latency is the cut alone, not the decode or the PNG encode.
