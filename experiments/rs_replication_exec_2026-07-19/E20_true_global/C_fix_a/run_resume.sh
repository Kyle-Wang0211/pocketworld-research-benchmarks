#!/bin/bash
# Resume after python3.14 pyexpat breakage: rerun matplotlib-dependent steps with python3.11.
# Fingerprints (npz), debt match, replays, colorize, meta already banked by the first chain.
set -u
PY=python3.11
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
C=$EXP/E20_true_global/C_fix_a
TF=$EXP/TRAILS_forensics
echo "=== RESUME START $(date -Iseconds)"
A_OK=1; B_OK=1
$PY $TF/detect_trails.py cap40 cap41 >> $C/a_trails.log 2>&1 || { echo "!! A trails rc=$?"; A_OK=0; }
[ $A_OK -eq 1 ] && { $PY $EXP/E3_birth_discipline/e3_birth_discipline.py cap40 cap41 >> $C/a_e3.log 2>&1 || { echo "!! A e3 rc=$?"; A_OK=0; }; }
echo "=== BRANCH A ok=$A_OK $(date +%H:%M:%S)"
$PY $TF/detect_trails.py cap50_fixA >> $C/b_trails.log 2>&1 || { echo "!! B trails rc=$?"; B_OK=0; }
[ $B_OK -eq 1 ] && { $PY $EXP/E3_birth_discipline/e3_birth_discipline.py cap50_fixA >> $C/b_e3.log 2>&1 || { echo "!! B e3 rc=$?"; B_OK=0; }; }
[ $B_OK -eq 1 ] && { $PY $C/make_f_rulers_fixa.py >> $C/b_rulers.log 2>&1 && $PY $C/f_rulers_fixa.py >> $C/b_rulers.log 2>&1 || { echo "!! B rulers rc=$?"; B_OK=0; }; }
echo "=== RESUME DONE A=$A_OK B=$B_OK $(date -Iseconds)"
