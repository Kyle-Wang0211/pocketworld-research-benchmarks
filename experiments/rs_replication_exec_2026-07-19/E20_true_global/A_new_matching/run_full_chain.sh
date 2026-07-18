#!/bin/bash
# E20-A full chain (resume after agent-orphaned run died at cap51 600/1371):
# match cap51 -> match cap50 -> replay x3 each (run_e20a.sh) -> rulers.
# No resume inside s1 (writes db copy atomically at end), so caps rerun from scratch.
set -u
E20A=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E20_true_global/A_new_matching
cd "$E20A"
echo "=== CHAIN START $(date -Iseconds)"
python3 s1_select_and_match.py --cap=cap51 >> s1_cap51_resume.log 2>&1
rc1=$?
echo "=== cap51 match rc=$rc1 $(date +%H:%M:%S)"
python3 s1_select_and_match.py --cap=cap50 >> s1_cap50.log 2>&1
rc2=$?
echo "=== cap50 match rc=$rc2 $(date +%H:%M:%S)"
if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
  echo "!!! MATCH STAGE FAILED (rc1=$rc1 rc2=$rc2), aborting before replay"
  exit 1
fi
bash run_e20a.sh >> replays.log 2>&1
echo "=== replays rc=$? $(date +%H:%M:%S)"
python3 f_rulers.py > f_rulers_out.json 2> f_rulers.err
echo "=== rulers rc=$? $(date +%H:%M:%S)"
echo "=== CHAIN DONE $(date -Iseconds)"
