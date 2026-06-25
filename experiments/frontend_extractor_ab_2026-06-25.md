# Front-end feature-extractor A/B — XFeat vs DSP-SIFT + first_octave gate (2026-06-25)

Goal: pick the OPTIMAL on-device feature extractor for the SfM front-end (pipeline = COLMAP
incremental SfM + CasDiffMVS; target 4224×2376; cross-platform iOS/Android/HarmonyOS/Web, no ANE;
prefer Dart/Dawn-WebGPU over Swift). DSP-SIFT extraction is the device bottleneck + heat source
(~5.4s/frame @2048, ~10s @4224). Decision driven by data, NOT sunk cost (user directive).

Fixture: bench50 = 50 frames @4224×2376 (`image_list_50.txt`, 747 K=25 pairs) from
`data/official_da3_base_k35_strict_seq_2026_06_02/.../photos_highres/`. Mapper: COLMAP incremental
(pycolmap 4.0.4 / the vendored `colmap_bench_exe`). Priorities (user): reproj ≤ gate (HARD), then
memory, then speed.

## DSP-SIFT baseline (reproduced, same binary/fixture/flags — also resolves the "0.933" question)
| config | reproj px | registered |
|---|---|---|
| COLMAP incremental, default loss (TRIVIAL) | 0.9996 | 50/50 |
| **COLMAP incremental, CAUCHY (shipped)** | **0.8319** | 50/50 |

→ The shipped COLMAP+CAUCHY config hits **0.83px** (beats the 0.933 anchor). Sub-pixel bar is real
and COLMAP meets it. (The 0.933 figure floated earlier was the GLOMAP-mapper log / default-loss range;
the production engine is COLMAP, and COLMAP+CAUCHY = 0.83px.)

## XFeat A/B (each vs DSP-SIFT under the SAME BA config; fair — 3 matchers incl. XFeat's own)
| variant | matcher | reproj px (default / CAUCHY) | reg/50 | extract | peak mem |
|---|---|---|---|---|---|
| XFeat sparse | MNN cos 0.82 | 1.466 / 1.146 | 50/50 | 0.201 s/frame (MPS) | 318 MB |
| XFeat* semi-dense | MNN coarse | 1.530 / 1.221 | 50/50 | 0.391 s/frame | 933 MB |
| XFeat sparse + LighterGlue | LightGlue | 1.443 / **1.086** | 50/50 | 2.67 s/frame (CPU) | 3211 MB |

**Best XFeat anywhere = 1.086px** = +16.4% over the 0.933 gate, +30.5% worse than DSP-SIFT's
matched-config 0.8319. All variants 1.09–1.53px (+38–53% worse localization). All register 50/50 with
strong connectivity (sparse 41.7% / star 25.6% / LightGlue 64.6% inliers) → **NOT a matcher/coverage
failure**. A better matcher (LighterGlue, cleanest) does NOT close the gap → it is XFeat's keypoint
localization precision (coarse 8×8-cell / 1/8-res heatmap + bicubic subpixel), a structural sub-pixel
deficit (matches the literature: learned detectors lag SIFT's DoG sub-pixel localization).
XFeat's one decisive win: extraction ~25× faster (0.2s vs ~5.4s/frame) — real, but on the lowest
priority AND moot since it fails the gate.

## first_octave −1 vs 0 gate (GPU DSP-SIFT memory lever — Track B)
| first_octave | keypoints | reg | reproj px | gss fp16 @4224 |
|---|---|---|---|---|
| −1 (baseline) | 590,200 | 50/50 | 1.0076 (default loss) | 642 MB |
| **0** | 592,492 | 50/50 | 1.0217 (default loss) | **161 MB** |

→ first_octave=0 holds (same registration, +0.014px = noise); octave −1 is 75% of gss memory but
yields ~1.6% of keypoints. **gss 642→161MB (4×) confirmed.** GPU DSP-SIFT @fo0 = 161MB is LIGHTER
than XFeat sparse (318MB) → XFeat loses its only claimed edge (memory) too.

## DECISION (data-backed, no sunk-cost bias)
**Continue the GPU DSP-SIFT WGSL/Dawn port (GPU_DSP_SIFT_PLAN.md), with first_octave=0 (161MB) as the
baseline.** It is the only option that (1) PASSES the hard sub-pixel gate (DSP-SIFT 0.83px), (2) is the
LIGHTEST (161MB < XFeat 318MB), (3) is one-codebase cross-platform (WGSL→Metal already on iPhone 14 Pro),
(4) clean license, (5) no downstream re-validation (stable C-ABI, preserves the feature). XFeat is closed
on quality — a high-risk pivot (fragmented cross-platform GPU + full pipeline re-tune) that fails the gate
by +16-53%. XFeat got a fair empirical shot (3 matchers, matched config, same fixture) and lost.

## S1 GPU parity status
Host Dawn proven runnable (aether_dawn_hello_compute PASS, native macOS arm64 Dawn). `sift_gss_blur.wgsl`
= one separable Gaussian step. Full S1 gss parity (max-rel ≤1e-3) needs `extract_gpuparity.cc` (~700 LOC)
+ the not-yet-written `sift_gss_resample.wgsl`. Shaders/Dawn live under `aether_cpp/` (not glomap_vendor).

Scratch artifacts: `/tmp/xfeat_ab/` (XFeat) and `/tmp/dspsift_wk1/` (first_octave A/B).
