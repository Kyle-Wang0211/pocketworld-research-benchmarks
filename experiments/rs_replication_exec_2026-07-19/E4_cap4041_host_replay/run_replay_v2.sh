#!/bin/zsh
# E4 v2 · cap40/cap41 host replay + cap51 control.
#
# WHY NOT the DR6 exe: sfm_replay_stored_pairs_exe (sha 9583814f…) is cap51-PINNED —
# disassembly of its "stored replay input is incomplete" branch shows hardcoded
# guards `stored_matches bytes == 0x6b40 (=858*32)` and `nonempty_matches == 0x35a
# (=858)`, i.e. it only accepts cap51's exact pair DB. cap40 (1067 pairs) and
# cap41 (928 pairs) exit rc=5 before streaming (evidence: runs_pinned_exe_failed/).
#
# THIS exe: sfm_replay_bench_exe, sha256
#   7648090b9a93f2c7b856a45fe37c066ceeca309e82736f5f8b1123f66cbdb22b
# built Jul 16 21:11 from bench/sfm_replay_bench.cc (mtime Jul 16 19:30, un-pinned,
# generic completeness check) — SAME stored-pairs live-reuse pipeline (CMake:
# "aether_sfm_c.cc consumes exact stored matches and TVGs via AETHER_REPLAY_MATCH_DB;
# no host CPU rematching"). Link predates the Jul 17 10:30 aether_sfm_c.cc edits,
# so it embeds pre-alias behavior. Control run on cap51 (DR6 input, DR6 env face =
# all unset) validates it against the DR6 frozen-exe baseline before trusting
# cap40/41 numbers.
#
# cap40/41 runs use the PRODUCTION env face (Q8_env_audit.md, install arm):
#   AETHER_STREAM_TEMPORAL_ONLY=1  AETHER_LIVE_CAND_K_HOT=6  AETHER_TRACK_UPGRADE=1
#   AETHER_ENRICH_TARGETED=1  AETHER_ENRICH_PAIR_CAP=300  AETHER_STAGE1_ROUNDS_CAP=4
#   AETHER_GHOST_MASK=1   (everything else unset; --k=12 production k)
set -u
E4=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E4_cap4041_host_replay
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-incremental-ba-ab/sfm_replay_bench_exe
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
DR6IN=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_deepresearch_2026-07-19/DR6_rounds_curve/input

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
    echo "[mem] <3GiB available, sleeping 60s (E3 parallel batch)"; sleep 60
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3; shift 3
  local envs=("$@")
  local out=$E4/runs/$name
  rm -rf "$out"; mkdir -p "$out"
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp "$dbsrc/sfm_live.db" "$dbdir/sfm_live.db"
  [ -f "$dbsrc/sfm_live.db-wal" ] && cp "$dbsrc/sfm_live.db-wal" "$dbdir/sfm_live.db-wal"
  [ -f "$dbsrc/sfm_live.db-shm" ] && cp "$dbsrc/sfm_live.db-shm" "$dbdir/sfm_live.db-shm"
  wait_mem
  echo "=== RUN $name env=[${envs[*]:-none}] $(date +%H:%M:%S)"
  /usr/bin/time -l env "${envs[@]}" \
    "$EXE" "$dbdir/sfm_live.db" "$ledger" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  local rc=$?
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS|SOURCE)" "$out/run.log" || true
  tail -6 "$out/run.err" | grep -E "maximum resident|peak memory" || true
  echo "src_db_md5_after=$(md5 -q $dbsrc/sfm_live.db)"
  rm -rf "$dbdir"
}

run_one cap51_control "$DR6IN" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
run_one cap40 "$DATA/cap40/device_full_pull_2026-07-17" "$DATA/cap40/device_full_pull_2026-07-17/sfm_fed_frames.jsonl" "${PROD_ENV[@]}"
run_one cap41 "$DATA/cap41/device_db_pull_2026-07-17" "$DATA/cap41/device_db_pull_2026-07-17/sfm_fed_frames.jsonl" "${PROD_ENV[@]}"
echo "E4 v2 REPLAY DONE $(date +%H:%M:%S)"
