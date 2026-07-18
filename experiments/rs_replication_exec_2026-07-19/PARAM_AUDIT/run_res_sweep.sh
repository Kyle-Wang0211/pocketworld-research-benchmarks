#!/bin/bash
set -u
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
P=$EXP/PARAM_AUDIT
PY=python3.11
run() {
  local cap=$1 fed=$2 photos=$3 rund=$4
  for ms in 1280 2016; do
    $PY $P/colorize_at_res.py $rund $fed $photos $ms $P/${cap}_res${ms}.ply
  done
  $PY $P/colorize_1280_vs_fullres.py $rund $fed $photos $P/colorize_2016_vs_fullres_${cap}.json 2016
}
run cap51 $DATA/cap51/private_manifests/sfm_fed_frames.jsonl $DATA/cap51/device_full_pull_2026-07-17/photos_highres $EXP/E9_birth_alias/runs/cap51_off_r1
run cap50 $DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl $DATA/cap50/device_full_pull_2026-07-17/photos_highres $EXP/E9_birth_alias/runs/cap50_off_r1
echo "RES SWEEP DONE"
