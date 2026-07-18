#!/bin/bash
# E16 M2 low-parallax birth ban matrix — run_e9.sh/run_e12.sh recipe verbatim,
# EXE -> sfm_replay_bench_e16_exe, arm env -> AETHER_M2_LOWPARALLAX_BAN=1
# (+ AETHER_M2_LOWPARALLAX_MIN_RATIO for the sensitivity arms).
# off x3 baselines already banked in E9 runs (not rerun, per orchestrator rule).
# Recipe = E4 run_replay_v2.sh verbatim: production env face + --k=12
# --keep-session-db=0, db copied to per-run input_db (WAL/SHM), source db never written.
set -u
E16=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E16_m2_lowparallax
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_e16_exe
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
    echo "[mem] <3GiB available, sleeping 60s (E14 parallel)"; sleep 60
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3; shift 3
  local envs=("$@")
  local out=$E16/runs/$name
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
  grep -aE "m2-lowparallax" "$out/run.log" | tail -4 || true
  tail -6 "$out/run.err" | grep -E "maximum resident" || true
  rm -rf "$dbdir"
}

CAP50=$DATA/cap50/device_full_pull_2026-07-17
CAP50_LED=$CAP50/sfm_fed_frames.jsonl
CAP51DB=$DATA/cap51/replay_database
CAP51_LED=$DATA/cap51/private_manifests/sfm_fed_frames.jsonl

# main arms (default ratio 0.01 = ORB-SLAM2 shipped)
run_one cap51_m2 "$CAP51DB" "$CAP51_LED" AETHER_M2_LOWPARALLAX_BAN=1
run_one cap50_m2 "$CAP50" "$CAP50_LED" AETHER_M2_LOWPARALLAX_BAN=1
# off-parity on the E16 exe (env unset must sit inside the E9 off noise band)
run_one cap51_e16exe_envoff "$CAP51DB" "$CAP51_LED"
# threshold sensitivity (cap51 main testbed).
# ADAPTATION vs the签决 sweep (0.005/0.01/0.02), reason banked in analysis/:
# offline ratio distribution over the ACTUAL pair set (banked E9 off bins)
# shows min ratio = 0.0202 (cap51) / 0.0283 (cap50) -> 0.005 is strictly
# dominated by the 0.01 run's banned=0 (subset argument) and is dropped;
# 0.02 sits exactly on the boundary and IS run; 0.05 / 0.15 are added as the
# smallest thresholds that actually bite (0.9% / 9.2% of pairs) so the
# ghost-band vs wall-coverage exchange the user签决'd for can be priced at all.
run_one cap51_m2_r002 "$CAP51DB" "$CAP51_LED" AETHER_M2_LOWPARALLAX_BAN=1 AETHER_M2_LOWPARALLAX_MIN_RATIO=0.02
run_one cap51_m2_r005 "$CAP51DB" "$CAP51_LED" AETHER_M2_LOWPARALLAX_BAN=1 AETHER_M2_LOWPARALLAX_MIN_RATIO=0.05
run_one cap51_m2_r015 "$CAP51DB" "$CAP51_LED" AETHER_M2_LOWPARALLAX_BAN=1 AETHER_M2_LOWPARALLAX_MIN_RATIO=0.15
echo "E16 REPLAY MATRIX DONE $(date +%H:%M:%S)"
