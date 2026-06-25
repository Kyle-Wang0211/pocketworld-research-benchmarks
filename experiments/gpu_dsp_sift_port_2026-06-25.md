# GPU DSP-SIFT extraction port (WGSL/Dawn) — full results + 4224 streaming verdict

Date: 2026-06-25. Branch `gpu-sift-s1` (commits up to 974cd199). Goal: move on-device DSP-SIFT
feature extraction (the SfM front-end bottleneck + heat source) from CPU to GPU, cross-platform
(WGSL/Dawn → Metal/Vulkan/WebGPU), preserving VLFeat/COLMAP DSP-SIFT quality. Host = Apple M3 Pro
(absolutes are M3 Pro, NOT iPhone; ratios portable). Fixture: sift_test.jpg @4224×2376 + a 2nd 4224 frame.

## Pipeline ported — every stage on GPU, VLFeat-parity validated
| Stage | shader | VLFeat parity (measured) | CPU→GPU |
|---|---|---|---|
| gss build (resident) | sift_gss_blur + sift_gss_resample.wgsl | max-rel 2.18e-6 over 8oct×6lvl chained | ~270ms resident build |
| DoG + 26-nbr extremum | sift_dog_extrema_test.wgsl | recall/precision 1.000000 | — |
| Newton refine + peak/edge gate | sift_refine_gate.wgsl | recall/prec 1.0, median pos-err 0px | 190→9ms |
| nonExtremaSuppression | sift_nonextrema_suppress.wgsl | recall/prec 1.0 (spatial-grid DAG) | ~940-2080→~20-35ms (~85-117×) |
| affine-shape | sift_affine_shape.wgsl | rel-Frob median 1.6e-6, 0 decision flips | — |
| orientation (1-4× expand) | sift_orientation.wgsl | median 0.000065°, expansion 100% | ~955→~56-105ms (~13×) |
| DSP descriptor (math) | sift_dsp_descriptor.wgsl | cosine median 1.000000, p95 1.0 | — |
| descriptor warp-setup (S5b) | sift_descriptor_warp.wgsl | cosine median 1.0, level-pick fp32 vs fp64 100%/115k | replaces host fp64 warp |

**End-to-end vs VLFeat full vl_covdet:** keypoint recall/precision 0.996-0.998, descriptor cosine median
1.000000 (orientation-disambiguated p95 0.99997). **The full GPU pipeline is VLFeat-equivalent.** gss is
RESIDENT (321MB fp32, never round-tripped); host warp-setup + gss readback eliminated.

Notable engineering: affine workgroup-mem limit solved by patch-only fp32 storage + on-the-fly gradients
(no fp16/tiling); suppression order-dependence solved as a strict-DAG fixed point (alive[] iterate);
bit-replicated VLFeat fast-math (Quake rsqrt, fast_atan2, fast_expn LUT) for descriptor/orientation parity.

## e2e timing @4224 (M3 Pro; contended by a concurrent MetalSplatter during the final run — min-frame + A/B ratios are the defensible signal)
- CPU production-exact baseline (DSP-SIFT + suppression): ~5.8-7 s/frame
- Full-GPU (S5b, host-warp eliminated): **best 2237 ms = 2.49× cumulative; ~2.0× typical**
- Chain THROUGH orientation alone: ~550 ms/frame (fast, gss-resident)
- Remaining bottleneck: `warp_fill` materializes ~82k padded patch planes into a ~3.4GB concat the
  descriptor re-reads → **fusable into the descriptor (warp directly from resident gss in build_patch)
  for another ~1.5-2× → ~4×.** Plus single-command-buffer batching of the sync dispatches.

## VERDICT — 4224 strict real-time streaming is NOT feasible with full-quality DSP-SIFT on this path
- iPhone-scaled (~2.9× the M3 Pro CPU ratio; GPU ratio likely worse — fewer GPU cores): best ~6.5 s/frame;
  even with warp-fill fusion (~1.5s M3) → ~4.3 s iPhone. **vs the ~2s/frame dome-capture streaming budget
  = over by ~2-3×.**
- 2048 (~4× fewer pixels) → ~1.6 s iPhone → under 2s = streaming-feasible.
- Buffer limit: full 21k-kp warp concat = 3.47GB > Dawn 2GB; needs keypoint batching or 4GB device limit.

## The work is NOT wasted regardless of the streaming decision
- For the CURRENT production architecture (post-capture BATCH @4224), the GPU port is a clear ~2-4× win +
  moves the heat from CPU to GPU.
- The SAME GPU code at 2048 input is a streaming-feasible extractor — the port is the foundation for
  2048-streaming or a two-tier (2048 stream + 4224 finalize).

## Open: the breakthrough question (under active research 2026-06-25)
User requires <2s 4224 streaming (rejects 2048-only / two-tier). Researching whether ANY path reaches it:
faster SfM-grade extractors, GPU-opt SOTA beyond ~4×, real-time SfM/SLAM architectures (temporal track +
keyframe extraction + async), keypoint-count/foveation strategies, hardware-floor analysis. See the
follow-up synthesis.
