#!/bin/bash
# SPEED battle: LAPACK dense-tier A/B, heat-controlled by SAME-SESSION ALTERNATION
# (E=AETHER_DENSE_LAPACK=0 Eigen LLT, L==1 Accelerate LAPACK), 3 rounds each, 2 caps.
# Same exe 2e03c66b (homebrew libceres.dylib carries Accelerate — no rebuild needed).
# Honest prior from routing source: host inflection <=200 imgs => expect ~0 gain
# at cap51(105)/cap50(139); -65% anchor was ~400 cams. This run PRICES that claim.
set -u
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
S=$EXP/SPEED_lapack_colorize
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_exe
EXPECTED_SHA=2e03c66b50e1255692be2e47d313a079a313571fef1c4a9d5ca7e94512eb1c38
got=$(shasum -a 256 "$EXE" | awk '{print $1}')
[ "$got" = "$EXPECTED_SHA" ] || { echo "EXE SHA MISMATCH: $got"; exit 1; }
PROD=(AETHER_STREAM_TEMPORAL_ONLY=1 AETHER_LIVE_CAND_K_HOT=6 AETHER_TRACK_UPGRADE=1
      AETHER_ENRICH_TARGETED=1 AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4
      AETHER_GHOST_MASK=1)

run_one() {
  local cap=$1 arm=$2 r=$3 lapack=$4 dbsrc=$5 fed=$6
  local out=$S/runs/${cap}_${arm}_r${r}
  [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log" && { echo "SKIP ${cap}_${arm}_r${r}"; return; }
  rm -rf "$out"; mkdir -p "$out/input_db"
  cp "$dbsrc" "$out/input_db/sfm_live.db"
  env "${PROD[@]}" AETHER_DENSE_LAPACK=$lapack \
    "$EXE" "$out/input_db/sfm_live.db" "$fed" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  echo "${cap}_${arm}_r${r} rc=$? $(grep -o '"dense_backend":"[A-Z]*"' "$out/finalize_segments.json" | head -1) $(grep '^RESULT' "$out/run.log" | grep -o 'finalize_ms=[0-9.]*')"
  rm -rf "$out/input_db"
}

echo "=== AB START $(date -Iseconds)"
for r in 1 2 3; do
  run_one cap51 E $r 0 "$DATA/cap51/replay_database/sfm_live.db" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
  run_one cap51 L $r 1 "$DATA/cap51/replay_database/sfm_live.db" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
done
for r in 1 2 3; do
  run_one cap50 E $r 0 "$DATA/cap50/device_full_pull_2026-07-17/sfm_live.db" "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl"
  run_one cap50 L $r 1 "$DATA/cap50/device_full_pull_2026-07-17/sfm_live.db" "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl"
done
echo "=== AB RUNS DONE $(date +%H:%M:%S)"

PY=python3.11
CZ=$EXP/E20_true_global/A_new_matching/colorize_replay.py
$PY $CZ $S/runs/cap51_E_r1 "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl" "$DATA/cap51/device_full_pull_2026-07-17/photos_highres" $S/runs/cap51_E_r1/replay_finalize_rgb.ply
$PY $CZ $S/runs/cap51_L_r1 "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl" "$DATA/cap51/device_full_pull_2026-07-17/photos_highres" $S/runs/cap51_L_r1/replay_finalize_rgb.ply
$PY $CZ $S/runs/cap50_E_r1 "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl" "$DATA/cap50/device_full_pull_2026-07-17/photos_highres" $S/runs/cap50_E_r1/replay_finalize_rgb.ply
$PY $CZ $S/runs/cap50_L_r1 "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl" "$DATA/cap50/device_full_pull_2026-07-17/photos_highres" $S/runs/cap50_L_r1/replay_finalize_rgb.ply
$PY $S/rulers_ab.py
echo "=== AB DONE $(date -Iseconds)"
