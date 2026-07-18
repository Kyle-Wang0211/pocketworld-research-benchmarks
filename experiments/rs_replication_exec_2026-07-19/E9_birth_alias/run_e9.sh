#!/bin/bash
# E9-B birth-time alias arms A/B — cap50 (main) + cap51 (validation)
# Uses OTHERS' uncommitted arms (bench/aether_sfm_c.cc Jul17) via freshly relinked
# sfm_replay_bench_exe (sha256 943de5c6...93a9, relinked 2026-07-18 13:54, no source edits).
# Recipe = E4 run_replay_v2.sh verbatim: production env face + --k=12 --keep-session-db=0,
# db copied to per-run input_db (WAL/SHM included), source db never written.
set -u
E9=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E9_birth_alias
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-incremental-ba-ab/sfm_replay_bench_exe
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
    echo "[mem] <3GiB available, sleeping 60s (E7 parallel)"; sleep 60
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3; shift 3
  local envs=("$@")   # may be empty; bash3.2 + set -u needs ${envs[@]+...} idiom
  local out=$E9/runs/$name
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
  # regression red lines
  if grep -qE "must not contain duplicate matches|THROW_CHECK_LE" "$out/run.err"; then
    echo "!!! ASSERTION RED LINE HIT in $name"
  fi
  grep -aE "conflict-multiview|exact_site|site_birth|geometric.winner|site.owner" "$out/run.log" | tail -8 || true
  tail -6 "$out/run.err" | grep -E "maximum resident" || true
  rm -rf "$dbdir"
}

CAP50=$DATA/cap50/device_full_pull_2026-07-17
CAP50_LED=$CAP50/sfm_fed_frames.jsonl
CAP51DB=$DATA/cap51/replay_database
CAP51_LED=$DATA/cap51/private_manifests/sfm_fed_frames.jsonl

# ---- cap50 main ----
run_one cap50_off_r1 "$CAP50" "$CAP50_LED"
run_one cap50_off_r2 "$CAP50" "$CAP50_LED"
run_one cap50_off_r3 "$CAP50" "$CAP50_LED"
run_one cap50_conflict_mv       "$CAP50" "$CAP50_LED" AETHER_CONFLICT_MULTIVIEW_BIRTH=1
run_one cap50_conflict_mv_owner "$CAP50" "$CAP50_LED" AETHER_CONFLICT_MULTIVIEW_BIRTH=1 AETHER_CONFLICT_MULTIVIEW_SITE_OWNER=1
run_one cap50_exact_v2          "$CAP50" "$CAP50_LED" AETHER_EXACT_SITE_OWNER_V2=1
run_one cap50_geom_winner       "$CAP50" "$CAP50_LED" AETHER_EXACT_SITE_GEOMETRIC_WINNER=1
# ---- cap51 validation ----
run_one cap51_off_r1 "$CAP51DB" "$CAP51_LED"
run_one cap51_off_r2 "$CAP51DB" "$CAP51_LED"
run_one cap51_off_r3 "$CAP51DB" "$CAP51_LED"
run_one cap51_conflict_mv       "$CAP51DB" "$CAP51_LED" AETHER_CONFLICT_MULTIVIEW_BIRTH=1
run_one cap51_conflict_mv_owner "$CAP51DB" "$CAP51_LED" AETHER_CONFLICT_MULTIVIEW_BIRTH=1 AETHER_CONFLICT_MULTIVIEW_SITE_OWNER=1
run_one cap51_exact_v2          "$CAP51DB" "$CAP51_LED" AETHER_EXACT_SITE_OWNER_V2=1
run_one cap51_geom_winner       "$CAP51DB" "$CAP51_LED" AETHER_EXACT_SITE_GEOMETRIC_WINNER=1
echo "E9 REPLAY MATRIX DONE $(date +%H:%M:%S)"
