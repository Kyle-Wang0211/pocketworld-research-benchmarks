# Change: Official CasDiffMVS (upstream, official blendmvg weights) on the 132-frame room

## Objective

User request 2026-09-03: "试试 CasDiffMVS，先不要加数据库，就是原本的算法试试".
Run the unmodified upstream cvg/diffmvs CasDiffMVS with an official checkpoint
and the official fusion on the same 132-frame room, using the production COLMAP
cameras, at the user-signed OFFICIAL real-scene configuration.  No retrained
weights, no extra datasets, no PocketWorld 'o'-pipeline gates, no downsampling.

## Frozen identities

- Code: fresh clone of https://github.com/cvg/diffmvs at
  `cd10d5c282a9cabd45a2f64598cd2b990b408d35` (2025-12-24), Apache-2.0, on the
  5090 at `/root/casdiffmvs_official_20260903/diffmvs_upstream`.  The vendored
  copy in the research repo was NOT used for the model (its `models/*.py` and
  `filter.py` carry local speed-up patches; md5 differs from upstream).
- Checkpoint: official `casdiffmvs_blendmvg.ckpt` (DTU pretrain + BlendedMVG
  finetune; from the vendored `checkpoints_unz`), SHA-256 recorded in
  `out_blendmvg_768x576_nv10/ckpt.sha256`.  Licence: weights trained with DTU,
  not shippable; this is a quality test only, as the user asked.
- Input: `pose_ablation_20260818/mvs_P16k` (132 × 4032x3024 JPEG, per-image
  PINHOLE cams from the production sparse model, official 10-neighbour
  `pair.txt`); per-file SHA-256 list in `input.sha256`.  Same input as the
  08-20 four-arm comparison.
- Config (user-signed OFFICIAL, 08-17): loader `--max_h 576 --max_w 768`
  (768x576), `--num_view 10`, `--numdepth_initial 48 --numdepth 384`,
  `--scale 0 0.125 0.025`, `--sampling_timesteps 0 1 1`, `--ddim_eta 0 1 1`,
  `--stage_iters 1 3 3`, `--cost_dim_stage 4 4 4`, `--CostNum 0 4 4`,
  `--hidden_dim 0 32 20`, `--context_dim 32 32 16`, `--unet_dim 0 16 8`,
  `--min_radius 0.125 --max_radius 8`, seed 123; fusion `filter.py`
  `--photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0
  --geo_depth_thres 0.01` with the official depth averaging.
- Difference from the 08-20 four-arm run: that run used 896x512 with 4
  neighbours through a local driver; this run uses the upstream `test.py` path,
  768x576 and the official 10-view pair list.

## Result recorded 2026-09-03

- Wall time 2 min 54 s on RTX 5090 (inference ≈ 0.06 s/frame), peak RSS 10.7 GB.
- Fused points: 36,845,039 (per-frame final-mask survival ≈ 0.67–0.80).
- `pc.ply` SHA-256 `8767328f…383a2`; viewer POSITION `d14fd155…5f679b`,
  RGB `b5a93aa1…388fe8`.
- Page: `verdict_page/casdiffmvs_official_blendmvg_20260903/`.
- User verdict (2026-09-03, visual): "没有任何重影" — no ghosting at all; the
  known defect remains: the white wall sticks to the suitcase and backpack
  (textureless wall depth pulled toward foreground objects).  The user asked to
  combine CasDiffMVS with MapAnything → `combine-casdiffmvs-mapanything-prior-init`.
- The `dtu` official checkpoint is staged on the remote but not run.
