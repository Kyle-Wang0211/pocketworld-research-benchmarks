#!/bin/bash
# E19-B step ②: replay the "densified" (SHA-identical, proven) db copies with the
# UNMODIFIED baseline exe from the E12 dir (2e03c66b), E9 recipe verbatim.
set -u
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
OUTB=$EXP/E19_no_birth/B_match_enrichment
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_exe
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures

PROD_ENV=(AETHER_STREAM_TEMPORAL_ONLY=1 AETHER_LIVE_CAND_K_HOT=6
          AETHER_TRACK_UPGRADE=1 AETHER_ENRICH_TARGETED=1
          AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4
          AETHER_GHOST_MASK=1)

wait_mem() {
  while true; do
    local avail
    avail=$(vm_stat | awk '/Pages free|Pages inactive|Pages speculative/ {gsub("\\.","",$NF); s+=$NF} END {print s*16384}')
    echo "[mem] available_bytes=$avail"
    [ "$avail" -ge 3221225472 ] && break
    echo "[mem] <3GiB available, sleeping 60s (E18 parallel)"; sleep 60
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3
  local out=$OUTB/runs/$name
  [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log" && { echo "=== SKIP $name (done)"; return; }
  rm -rf "$out"; mkdir -p "$out"
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp "$dbsrc/sfm_live.db" "$dbdir/sfm_live.db"
  [ -f "$dbsrc/sfm_live.db-wal" ] && cp "$dbsrc/sfm_live.db-wal" "$dbdir/sfm_live.db-wal"
  [ -f "$dbsrc/sfm_live.db-shm" ] && cp "$dbsrc/sfm_live.db-shm" "$dbdir/sfm_live.db-shm"
  wait_mem
  echo "=== RUN $name $(date +%H:%M:%S)"
  {
    echo "started_at=$(date -Iseconds)"
    echo "arm=densified_db_control (db proven byte-identical to baseline; see inject_ledger.json)"
    echo "binary_sha256=$(shasum -a 256 "$EXE" | awk '{print $1}')"
    echo "input_db_sha256=$(shasum -a 256 "$dbdir/sfm_live.db" | awk '{print $1}')"
  } > "$out/manifest.txt"
  /usr/bin/time -l env "${PROD_ENV[@]}" \
    "$EXE" "$dbdir/sfm_live.db" "$ledger" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  local rc=$?
  echo "exit_code=$rc" >> "$out/manifest.txt"
  echo "finished_at=$(date -Iseconds)" >> "$out/manifest.txt"
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS|IMPORTED_STORED_GRAPH|SOURCE)" "$out/run.log" || true
  if grep -qE "must not contain duplicate matches|THROW_CHECK_LE" "$out/run.err"; then
    echo "!!! ASSERTION RED LINE HIT in $name"
  fi
  tail -6 "$out/run.err" | grep -E "maximum resident" || true
  rm -rf "$dbdir"
}

run_one cap50_densified "$OUTB/cap50_injected_db" "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl"
run_one cap51_densified "$OUTB/cap51_injected_db" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
echo "E19-B RUNS DONE $(date +%H:%M:%S)"
