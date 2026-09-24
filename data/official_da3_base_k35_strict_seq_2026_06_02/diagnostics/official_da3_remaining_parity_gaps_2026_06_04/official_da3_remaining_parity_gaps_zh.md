# Official DA3 remaining parity gaps ledger

日期：2026-06-04

## 目的

这份 ledger 只记录“仍未 100% official parity”的项目。它把差异分成三类：

- **Official baseline gap**：还没完全复刻官方语义，应该继续对齐。
- **Research gate**：需要 reference A/B 或外部硬件/官方更新才能证明。
- **Product adaptation**：明确不是官方复刻，是未来移动端产品层优化。

## 当前已锁定的 baseline

PocketWorld canonical official baseline：

- Model：commercial-safe `DA3-BASE`
- Runtime：APP/CoreML product path
- Window：K35 / overlap 18, because mobile/ordinary laptop cannot carry official 120/60
- Output path：`results_output/frame_*.npz + npz_output_process.py`
- Frame selection：only official non-overlap/core frames
- Confidence：DA3-Streaming `conf -= 1.0`
- Downstream threshold：global `mean(conf) * 0.5`
- Sample：global `sample_ratio=0.015`
- No cleanup：no voxel / TSDF / surfel / statistical pruning / normal filtering

`0.75` is retained only as DA3-Streaming `Pointcloud_Save` full-chunk PLY config / sensitivity reference, not as the canonical core-frame npz baseline.

## Gap ledger

| ID | Gap | Class | Current evidence | Risk | Next action |
|---|---|---|---|---|---|
| G1 | Full same-resolution official PyTorch K35 hard parity is not closed | Research gate | MPS fails at `process_res=742` with `89.01 GiB`; `476` with `15.36 GiB`; `252` succeeds | Cannot fully prove whether official PyTorch full-res K35 is also thick | Use `official_pytorch_fullres_gate_runbook_2026_06_04`; A100/H100 only for one-time reference |
| G2 | K35/18 differs from official 120/60 | Product adaptation / research constraint | Mobile route cannot carry 120/60; current route is K35/18 | Official context length and overlap constraints differ | Keep K35 as mobile constraint; do not call it exact official default |
| G3 | CoreML sealed model vs official PyTorch output is not fully equal at K35 full-res | Research gate | small-K parity is good for pose/depth scale; K35 low-res trend does not show CoreML-only blow-up | If PyTorch full-res is clean, CoreML export/preprocess may still be culprit | Close G1 or run more mid-res trend gates where memory allows |
| G4 | Fixed `742x476` input vs official highres dynamic `upper_bound_resize` | Research gate | K35 low-res fixed/highres PyTorch bbox ratio `1.067664`; not catastrophic but visible | Fixed aspect/input contract may thicken geometry or distort shape | Continue fixed vs highres A/B; do not change product input until evidence is strong |
| G5 | CoreML ref-view / internal model export equivalence is not directly observable | Research gate | Official uses `ref_view_strategy=saddle_balanced`; sealed CoreML behavior inferred through outputs | Wrong ref-view behavior could affect pose/depth consistency | Treat full K35 output parity as the practical observable |
| G6 | Confidence distribution still differs between CoreML and PyTorch | Research gate | small-K confidence MAE around `2.23145`, Pearson around `0.863117`; valid fraction can be made similar | Thresholded point selection may differ even when geometry is similar | Keep recording `confidenceMode`, offset, threshold, valid fraction in every report |
| G7 | Adjacent dense Sim3 must remain production-gated before global pointcloud | Official baseline gap | APP now blocks pointcloud if dense Sim3 / streaming alignment not ready | Silent identity fallback would produce wrong multi-window geometry | Keep gate; extend real capture tests when full 414 run is stable |
| G8 | Loop closure path is not exact official SALAD + FAISS + Sim3LoopOptimizer | Commercial constraint / research gate | SALAD is not product-safe; SelaVPR++ is selected commercial-safe backend | Loop behavior may differ; cannot claim 1:1 official loop | Keep loop as verified constraints only; label SelaVPR++ as commercial-safe adaptation |
| G9 | `pcd/combined_pcd.ply` remains a misleading official path | Documentation / baseline risk | Official CLI full-chunk merge retains overlap slots; APP chooses core-frame npz path | Comparing APP output to `combined_pcd.ply` can mislead diagnosis | Always state which official path is being compared |
| G10 | Product cleanup is not allowed inside official baseline | Product adaptation | No official downstream dedupe found; K35 thickness likely upstream | Adding cleanup now would hide parity errors | Only add cleanup after baseline is frozen, with product-layer label |
| G11 | Frame order must be stable when running official scripts | Official baseline gap | Official CLI often uses sorted file paths; APP uses timestamp/order metadata | Lexicographic ordering can break temporal sequence | Use zero-padded manifests / renamed files for official runner parity |
| G12 | Random reservoir sampling seed differs from official | Minor implementation gap | Official `np.random` has no explicit pointcloud seed; APP uses fixed product seed | Exact PLY point identity may differ while distribution matches | Keep reports explicit: official rule, product-fixed seed |
| G13 | DA3-LARGE-1.1 license metadata conflict | Commercial gate | GitHub README says CC BY-NC; HF card/API currently says Apache | Product could accidentally adopt an unresolved checkpoint | Keep product locked to DA3-BASE until upstream license is clarified |
| G14 | Mobile/tablet/laptop product viability is not proven by Mac research executor | Product gate | New `da3_mobile_viability_gate.py` reports the current Research sample as `warning`: depth completed 414/414, but no APP real-device audit, no sample-path pointcloud report, and no explicit product thresholds | Could mistake a research pass for product feasibility, or mistake A100 reference need for product dependency | Run real APP captures on target devices and evaluate with explicit latency/memory/thermal thresholds |

## Practical decision

Do not discard DA3 merely because the official PyTorch reference path wants a large buffer on this Mac. That memory number is a research gate, not the product path.

Do discard or demote DA3 for local product use if the actual APP/CoreML path cannot meet target latency, memory, battery, thermal, or quality on target phones/tablets/laptops after the official baseline is frozen.

## What counts as done

The official replication phase can only be considered sufficiently closed when:

1. APP core-frame downstream remains locked to `npz_output_process.py` semantics.
2. K35 windowing, save slots, confidence offset, global threshold, sample ratio, C2W camera poses, depth scale, and dense Sim3 gate are all tested.
3. The full-res PyTorch reference gate is either closed, or explicitly waived as an external research blocker with low-res trend evidence preserved.
4. Any cleanup/thinning/fusion is introduced only under a product-layer flag and never described as hidden official DA3 behavior.
5. Product viability is separately evaluated on target devices with `da3_mobile_viability_gate.py`; Mac research executor completion alone does not count.
