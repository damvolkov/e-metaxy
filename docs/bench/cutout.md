# Bench: cutting ink out of a photo

Decision record for `image/cutout` (2026-11-05). Raw samples, generator and arm scripts are in
[`cutout/`](cutout/): `gen.py.txt` (the synthetic photos), `base.py.txt`, `a.py.txt`, `c.py.txt` (the arms), `run.py.txt` (the
interleaved runner), `port.py.txt` (the equivalence check of the port below), and for the form-lines section `gen2.py.txt`, `a2.py.txt`, `l.py.txt`, `run2.py.txt`, `analyse.py.txt`, `tune.py.txt`, `tune.out.txt`, `port2.py.txt` — the scripts verbatim as they ran, kept as text so the linters leave them be —, `test.tsv` and `dev.tsv` (one row per image and arm: `image, arm, ms, F, IoU`) and, for form lines, `dev-lined`, `dev-plain`, `test-lined`, `test-plain`, `test-legacy`, `test-flourish` (`.tsv`).

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

## Form lines (2026-11-05)

Found live: the grey line of a photographed form entered as ink. The shipped arm A takes any dark run for ink, so a
printed line darker than its gate (flat < 150) is cut with the signature.

**Pre-registered** (before any run). Hypothesis: removing the long straight runs of the ink mask, and bridging the gap
they leave in a stroke that crosses them, raises F on photos with dark printed lines and costs nothing on photos without.
Primary metric: F-measure per image against the exact mask, paired, **BCa bootstrap 95 %** (20 000 resamples). Land only if
(a) on the lined test set the interval's lower bound is above 0, and (b) on the line-free test set the lower bound is above
**-0.03**. If either fails, nothing lands.

| arm | what |
|---|---|
| **A** | the shipped cut-out: `a2.py.txt` (Sauvola by `cv2.boxFilter`, the port; its median F on the old test set is the 0.909 above) |
| **L** | A, then `cv2.HoughLinesP` (1 px, 0.5 degrees) over the ink mask: a segment of at least 25 % of the longer side, 200 votes, gap 6, is a line; drawn 5 px thick it is taken off the mask, and a 9 px closing restores the pixels of a stroke that had ink on both sides |

Both arms run in the one `env-a` (opencv-python-headless 5.0.0.93, numpy 2.5.4, Python 3.14): L is A plus a step, so there
is no second dependency to fence. Machine and interleaving as above (3 warm-ups discarded; one worker process per arm).

Data (`gen2.py.txt`, seeds fixed): **lined** photos — a dark line (0.2-0.4 x the paper's grey, 2-3 px, tilted by the
perspective) placed across the signature, half with a parallel line, half with a vertical box edge; **plain** photos — the
same generator without any line. 20 dev and 60 test images of each (lined: seeds 11 and 12; plain: 1 and 2). L's four
parameters were chosen on dev only, by the grid in `tune.out.txt` (a 0.15 x length cut 0.02-0.04 F on plain photos — the
Hough transform found lines inside the strokes — 0.25 and above cost nothing).

| set (60 test images) | A F | L F | L - A on F, 95 % CI | L wins / loses | A ms p50 | L ms p50 |
|---|---|---|---|---|---|---|
| lined | 0.686 | **0.929** | **+0.236 [+0.214, +0.259]** | 60 / 0 | 25 | 32 |
| plain | 0.953 | 0.953 | +0.000 (identical on every image: no line found) | 0 / 0 | 23 | 27 |
| old test set (weak line) | 0.909 | 0.931 | +0.016 [+0.009, +0.027] | 14 / 0 | 23 | 27 |

IoU on lined: 0.522 -> 0.868 (+0.321 [+0.296, +0.347]).

**Verdict: land L.** (a) holds by far (+0.214 lower bound), (b) holds trivially (0 on every plain image, lower bound far
above -0.03). It costs about 5 ms a photo. The adapter is the arm to the letter: on all 220 bench images (dev and test, lined,
plain and flourish) the ink mask of the adapter against the bench arm L has pixel IoU 1.000000 (`port2.py.txt`).

**Exploratory, not pre-registered, and a loss.** A signature with its own long straight underline (`test-flourish`: 300-600 px,
3 px, in the mask) is read by L as a printed line and erased: F 0.958 -> 0.819, **-0.143 [-0.155, -0.130]**, A better on 58
of 60. The gate cannot tell a printed line from a straight flourish: both are long, thin, dark and straight. Landed anyway
because a form line is the common case (and the live failure), a straight 300 px flourish is the rarer one; the cost is
named here, not hidden.

## Limits

- **Synthetic only.** No public dataset of signature photos with masks exists (DIBCO are scans); there are no real photos
  in the bench yet. The scores are a ranking of the arms on a generator, not a promise on a phone.
- The generator's **paper tint is unrealistically strong**, which favours any method that flattens the background.
- The original generator's form line (0.55 × the paper's grey) mostly blurs out of the gate; the dark ones are measured in
  "Form lines" above, on a generator of the same family — lines it draws are straight and clean, a real form's are printed
  dashes, boxes and stamps: untested.
- Latency is the cut alone, not the decode or the PNG encode.
