#!/bin/zsh
# E4 · cap40/cap41 host replay — self-consistent baseline (device finalize was a
# full re-solve inconsistent with pulled live db; see S1 db_meta_consistency.json).
# Exe = frozen §4.2 harness sha256 9583814f7a095fcb4896259aeae91e581936628a1fb8602071d39826b21d921e
# Command-line format copied from DR6_rounds_curve/run_sweep.sh (cap51 precedent).
# Env face = production install arm (Q8_env_audit.md), NOT the DR6 minimal face:
#   AETHER_STREAM_TEMPORAL_ONLY=1  AETHER_LIVE_CAND_K_HOT=6  AETHER_TRACK_UPGRADE=1
#   AETHER_ENRICH_TARGETED=1  AETHER_ENRICH_PAIR_CAP=300  AETHER_STAGE1_ROUNDS_CAP=4
#   AETHER_GHOST_MASK=1   (everything else unset; --k=12 production k)
set -u
E4=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E4_cap4041_host_replay
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-incremental-ba-ab/sfm_replay_stored_pairs_exe
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures

wait_mem() {
  # available = (free + inactive + speculative) pages * 16384; wait if < 3 GiB (E3 parallel batch)
  while true; do
    local avail
    avail=$(vm_stat | awk '/Pages free|Pages inactive|Pages speculative/ {gsub("\\.","",$NF); s+=$NF} END {print s*16384}')
    echo "[mem] available_bytes=$avail"
    [ "$avail" -ge 3221225472 ] && break
    echo "[mem] <3GiB available, sleeping 60s (E3 parallel batch)"; sleep 60
  done
}

run_one() {
  local cap=$1 srcdir=$2
  local out=$E4/runs/$cap
  rm -rf "$out"; mkdir -p "$out"
  # fresh copy of the frozen input db per run (ABI may write session state;
  # source stays byte-identical, md5 re-checked after the run)
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp "$srcdir/sfm_live.db" "$dbdir/sfm_live.db"
  [ -f "$srcdir/sfm_live.db-wal" ] && cp "$srcdir/sfm_live.db-wal" "$dbdir/sfm_live.db-wal"
  [ -f "$srcdir/sfm_live.db-shm" ] && cp "$srcdir/sfm_live.db-shm" "$dbdir/sfm_live.db-shm"
  wait_mem
  echo "=== RUN $cap $(date +%H:%M:%S)"
  /usr/bin/time -l env \
    AETHER_STREAM_TEMPORAL_ONLY=1 \
    AETHER_LIVE_CAND_K_HOT=6 \
    AETHER_TRACK_UPGRADE=1 \
    AETHER_ENRICH_TARGETED=1 \
    AETHER_ENRICH_PAIR_CAP=300 \
    AETHER_STAGE1_ROUNDS_CAP=4 \
    AETHER_GHOST_MASK=1 \
    "$EXE" "$dbdir/sfm_live.db" "$srcdir/sfm_fed_frames.jsonl" "$out" --k=12 \
    > "$out/run.log" 2> "$out/run.err"
  local rc=$?
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS)" "$out/run.log" || true
  tail -6 "$out/run.err" | grep -E "maximum resident|peak memory" || true
  md5 -q "$srcdir/sfm_live.db"
  rm -rf "$dbdir"
  rm -f "$out/session.db" "$out/session.db-wal" "$out/session.db-shm"
}

run_one cap40 $DATA/cap40/device_full_pull_2026-07-17
run_one cap41 $DATA/cap41/device_db_pull_2026-07-17
echo "E4 REPLAY DONE $(date +%H:%M:%S)"
