#!/bin/sh
set -eu

repo="/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
experiment="$repo/experiments/full_stack_visual_2026-07-16"
output="$experiment/runs/strict_final/cap41"
mkdir -p "$output"

exec /opt/homebrew/bin/python3.11 "$experiment/assemble_full_stack.py" \
  --device-sparse /tmp/pw_device_exact_evidence_20260716/cap41/sfm_sparse.ply \
  --device-meta /tmp/pw_device_exact_evidence_20260716/cap41/sfm_sparse_meta.json \
  --ghost-sparse /tmp/pw_full_stack_20260716/colorized/cap41_ghost_owner_full_truecolor.ply \
  --ghost-poses /tmp/pw_full_stack_20260716/cap41/ghost_owner_full/solved_poses.csv \
  --replay-ledger "$repo/data/pocketworld_captures/cap41/device_2026-07-16/sfm_fed_frames.jsonl" \
  --replay-to-metric-manifest "$experiment/runs/d_final/cap41/metric_transform_manifest.json" \
  --metric-to-raw-manifest "$experiment/runs/d_final/cap41/raw_transform_manifest.json" \
  --b-floor /tmp/pw_full_stack_20260716/cap41/cap41_b_floor_1cm_raw.ply \
  --b-floor-gauge device_raw \
  --b-wall /tmp/pw_full_stack_20260716/cap41/cap41_b_wall_1cm_raw.ply \
  --b-wall-gauge device_raw \
  --d-cloud "$experiment/runs/d_final/cap41/d_births_device_raw_gauge.ply" \
  --d-cloud-gauge device_raw \
  --require-b-floor --require-b-wall --require-d \
  --strict-final --review-classification STRICT_FULL --capture-name cap41 \
  --ghost-provenance-json "$experiment/runs/d_final/cap41/ghost_provenance.json" \
  --b-floor-provenance-json "$experiment/runs/d_final/cap41/b_floor_provenance.json" \
  --b-wall-provenance-json "$experiment/runs/d_final/cap41/b_wall_provenance.json" \
  --d-certificate-json "$experiment/runs/d_final/cap41/d_final_stack_certificate.json" \
  --d-asset-inventory-json "$experiment/runs/d_final/cap41/d_asset_inventory.json" \
  --ghost-env AETHER_PUBLISH_GATE=0 \
  --ghost-env AETHER_PUBLISH_DEPTH_CONFLICT_OWNER=1 \
  --ghost-env AETHER_PUBLISH_DEPTH_OWNER_ERROR_FIRST=1 \
  --ghost-env AETHER_EXACT_SITE_OWNER_MIN_DEPTH_M=0.012 \
  --c-backend-json "$experiment/runs/c_backend/c_backend_certificate.json" \
  --expected-registered 102 --expected-frame-count 102 \
  --output-ply "$output/full_stack_truecolor_device_raw.ply" \
  --output-manifest "$output/full_stack_manifest.json"
