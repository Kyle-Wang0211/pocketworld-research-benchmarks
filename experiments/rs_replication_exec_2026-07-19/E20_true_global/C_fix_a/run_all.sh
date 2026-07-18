#!/bin/bash
# Master chain, two independent branches:
#   A: E3 on cap40/41 (fingerprints -> trails -> e3)
#   B: cap50 fix-A rehearsal (debt match -> replays x3 -> colorize -> meta -> E3 on top -> rulers)
set -u
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
C=$EXP/E20_true_global/C_fix_a
TF=$EXP/TRAILS_forensics
mkdir -p $TF/cap40 $TF/cap41 $TF/cap50_fixA
echo "=== CHAIN START $(date -Iseconds)"

echo "=== BRANCH A: E3 on cap40/41"
A_OK=1
python3 $TF/compute_fingerprints.py cap40 cap41 >> $C/a_fingerprints.log 2>&1 || { echo "!! A fingerprints rc=$?"; A_OK=0; }
if [ $A_OK -eq 1 ]; then
  python3 $TF/detect_trails.py cap40 cap41 >> $C/a_trails.log 2>&1 || { echo "!! A trails rc=$?"; A_OK=0; }
fi
if [ $A_OK -eq 1 ]; then
  python3 $EXP/E3_birth_discipline/e3_birth_discipline.py cap40 cap41 >> $C/a_e3.log 2>&1 || { echo "!! A e3 rc=$?"; A_OK=0; }
fi
echo "=== BRANCH A done ok=$A_OK $(date +%H:%M:%S)"

echo "=== BRANCH B: cap50 fix-A"
B_OK=1
python3 $C/s2_match_debt.py >> $C/b_match.log 2>&1 || { echo "!! B debt match rc=$?"; B_OK=0; }
if [ $B_OK -eq 1 ]; then
  bash $C/run_debt_replays.sh >> $C/b_replays.log 2>&1 || { echo "!! B replays rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  python3 $EXP/E20_true_global/A_new_matching/colorize_replay.py \
    $C/runs/cap50_debt_r1 \
    $DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl \
    $DATA/cap50/device_full_pull_2026-07-17/photos_highres \
    $C/runs/cap50_debt_r1/replay_finalize_rgb.ply >> $C/b_colorize.log 2>&1 || { echo "!! B colorize rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  python3 $C/make_meta_from_solved.py >> $C/b_meta.log 2>&1 || { echo "!! B meta rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  mkdir -p $C/cap50_fixA_inputs
  ln -sf $C/cap50_debtfix_db/sfm_live.db $C/cap50_fixA_inputs/sfm_live.db
  ln -sf $C/runs/cap50_debt_r1/replay_finalize_rgb.ply $C/cap50_fixA_inputs/sfm_sparse.ply
  ln -sf $DATA/cap50/device_full_pull_2026-07-17/ghost_mask.json $C/cap50_fixA_inputs/ghost_mask.json
  python3 $TF/compute_fingerprints.py cap50_fixA >> $C/b_fingerprints.log 2>&1 || { echo "!! B fingerprints rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  python3 $TF/detect_trails.py cap50_fixA >> $C/b_trails.log 2>&1 || { echo "!! B trails rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  python3 $EXP/E3_birth_discipline/e3_birth_discipline.py cap50_fixA >> $C/b_e3.log 2>&1 || { echo "!! B e3 rc=$?"; B_OK=0; }
fi
if [ $B_OK -eq 1 ]; then
  python3 $C/make_f_rulers_fixa.py >> $C/b_rulers.log 2>&1 && \
  python3 $C/f_rulers_fixa.py >> $C/b_rulers.log 2>&1 || { echo "!! B rulers rc=$?"; B_OK=0; }
fi
echo "=== BRANCH B done ok=$B_OK $(date +%H:%M:%S)"
echo "=== CHAIN DONE A=$A_OK B=$B_OK $(date -Iseconds)"
