#!/bin/zsh
# DR6 stage-1 rounds cost curve — cap51 host replay sweep.
# Single variable: AETHER_STAGE1_ROUNDS_CAP (unset baseline, then 1..5).
# Exe = frozen §4.2 harness (sha 9583814f...), stored-pairs replay, CPU match.
set -u
DR6=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_deepresearch_2026-07-19/DR6_rounds_curve
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-incremental-ba-ab/sfm_replay_stored_pairs_exe
LEDGER=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap51/private_manifests/sfm_fed_frames.jsonl

wait_mem() {
  # available = (free + inactive + speculative) pages * 16384; wait if < 3 GiB
  while true; do
    local avail
    avail=$(vm_stat | awk '/Pages free|Pages inactive|Pages speculative/ {gsub("\\.","",$NF); s+=$NF} END {print s*16384}')
    echo "[mem] available_bytes=$avail"
    [ "$avail" -ge 3221225472 ] && break
    echo "[mem] <3GiB available, sleeping 60s (E1 parallel batch)"; sleep 60
  done
}

run_one() {
  local name=$1 capval=$2
  local out=$DR6/runs/$name
  rm -rf "$out"; mkdir -p "$out"
  # fresh copy of the committed input db per run (the ABI may write session
  # state; the source stays byte-identical, verified after the sweep)
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp $DR6/input/sfm_live.db $dbdir/sfm_live.db
  cp $DR6/input/sfm_live.db-wal $dbdir/sfm_live.db-wal
  wait_mem
  echo "=== RUN $name AETHER_STAGE1_ROUNDS_CAP=${capval:-unset} $(date +%H:%M:%S)"
  if [ -n "$capval" ]; then
    /usr/bin/time -l env AETHER_STAGE1_ROUNDS_CAP=$capval \
      "$EXE" "$dbdir/sfm_live.db" "$LEDGER" "$out" --k=12 \
      > "$out/run.log" 2> "$out/run.err"
  else
    /usr/bin/time -l \
      "$EXE" "$dbdir/sfm_live.db" "$LEDGER" "$out" --k=12 \
      > "$out/run.log" 2> "$out/run.err"
  fi
  local rc=$?
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS)" "$out/run.log" || true
  tail -6 "$out/run.err" | grep -E "maximum resident|peak memory" || true
  # keep evidence small-ish: drop the per-run db copy (source input/ is canonical)
  rm -rf "$dbdir"
  rm -f "$out/session.db" "$out/session.db-wal" "$out/session.db-shm"
}

run_one base ""
run_one cap1 1
run_one cap2 2
run_one cap3 3
run_one cap4 4
run_one cap5 5
echo "SWEEP DONE $(date +%H:%M:%S)"
md5 -q $DR6/input/sfm_live.db $DR6/input/sfm_live.db-wal
