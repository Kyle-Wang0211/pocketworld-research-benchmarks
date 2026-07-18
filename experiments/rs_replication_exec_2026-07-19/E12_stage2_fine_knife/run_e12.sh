#!/bin/bash
# E12-B stage-2 fine-knife matrix — run_e9.sh recipe verbatim, EXE -> sfm_replay_bench_e12_exe,
# arm env -> AETHER_STAGE2_MERGE_TRANSFER=1. off x3 baselines already banked in E9 runs (not rerun).
# Recipe = E4 run_replay_v2.sh verbatim: production env face + --k=12 --keep-session-db=0,
# db copied to per-run input_db (WAL/SHM included), source db never written.
set -u
E12=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E12_stage2_fine_knife
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_e12_exe
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
    echo "[mem] <3GiB available, sleeping 60s"; sleep 60
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3; shift 3
  local envs=("$@")
  local out=$E12/runs/$name
  [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log" && { echo "=== SKIP $name (done)"; return; }
  rm -rf "$out"; mkdir -p "$out"
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp "$dbsrc/sfm_live.db" "$dbdir/sfm_live.db"
  [ -f "$dbsrc/sfm_live.db-wal" ] && cp "$dbsrc/sfm_live.db-wal" "$dbdir/sfm_live.db-wal"
  [ -f "$dbsrc/sfm_live.db-shm" ] && cp "$dbsrc/sfm_live.db-shm" "$dbdir/sfm_live.db-shm"
  wait_mem
  echo "=== RUN $name env=[${envs[*]:-prod-only}] $(date +%H:%M:%S)"
  {
    echo "started_at=$(date -Iseconds)"
    echo "arm_env=${envs[*]:-none}"
    echo "binary_sha256=$(shasum -a 256 "$EXE" | awk '{print $1}')"
    echo "input_db_sha256=$(shasum -a 256 "$dbdir/sfm_live.db" | awk '{print $1}')"
  } > "$out/manifest.txt"
  /usr/bin/time -l env "${PROD_ENV[@]}" ${envs[@]+"${envs[@]}"} \
    "$EXE" "$dbdir/sfm_live.db" "$ledger" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  local rc=$?
  echo "exit_code=$rc" >> "$out/manifest.txt"
  echo "finished_at=$(date -Iseconds)" >> "$out/manifest.txt"
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS|SOURCE)" "$out/run.log" || true
  if grep -qE "must not contain duplicate matches|THROW_CHECK_LE" "$out/run.err"; then
    echo "!!! ASSERTION RED LINE HIT in $name"
  fi
  grep -aE "stage2-merge-transfer" "$out/run.log" | tail -4 || true
  tail -6 "$out/run.err" | grep -E "maximum resident" || true
  rm -rf "$dbdir"
}

CAP50=$DATA/cap50/device_full_pull_2026-07-17
CAP50_LED=$CAP50/sfm_fed_frames.jsonl
CAP51DB=$DATA/cap51/replay_database
CAP51_LED=$DATA/cap51/private_manifests/sfm_fed_frames.jsonl

run_one cap51_stage2 "$CAP51DB" "$CAP51_LED" AETHER_STAGE2_MERGE_TRANSFER=1
run_one cap50_stage2 "$CAP50" "$CAP50_LED" AETHER_STAGE2_MERGE_TRANSFER=1
echo "E12 REPLAY MATRIX DONE $(date +%H:%M:%S)"
