#!/bin/bash
# E20-C fix-A: replay the debt-repaid db x3 with the UNMODIFIED baseline exe
# (2e03c66b, E9 recipe verbatim — same as run_e20a.sh).
set -u
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
OUTC=$EXP/E20_true_global/C_fix_a
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_exe
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
EXPECTED_SHA=2e03c66b50e1255692be2e47d313a079a313571fef1c4a9d5ca7e94512eb1c38

got=$(shasum -a 256 "$EXE" | awk '{print $1}')
[ "$got" = "$EXPECTED_SHA" ] || { echo "EXE SHA MISMATCH: $got"; exit 1; }

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
    sleep 20
  done
}

run_one() {
  local name=$1 dbsrc=$2 ledger=$3
  local out=$OUTC/runs/$name
  [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log" && { echo "=== SKIP $name (done)"; return; }
  rm -rf "$out"; mkdir -p "$out"
  local dbdir=$out/input_db
  mkdir -p "$dbdir"
  cp "$dbsrc/sfm_live.db" "$dbdir/sfm_live.db"
  wait_mem
  echo "=== RUN $name $(date +%H:%M:%S)"
  {
    echo "started_at=$(date -Iseconds)"
    echo "arm=fix_a_debt_repaid (K12 certified-schedule starved pairs matched+injected; see debt_ledger.json)"
    echo "binary_sha256=$(shasum -a 256 "$EXE" | awk '{print $1}')"
    echo "input_db_sha256=$(shasum -a 256 "$dbdir/sfm_live.db" | awk '{print $1}')"
  } > "$out/manifest.txt"
  /usr/bin/time -l env "${PROD_ENV[@]}" \
    "$EXE" "$dbdir/sfm_live.db" "$ledger" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  local rc=$?
  echo "exit_code=$rc" >> "$out/manifest.txt"
  echo "rc=$rc"
  grep -E "^(RESULT|STREAMED|REFINED|STORED_PAIRS|IMPORTED_STORED_GRAPH|SOURCE)" "$out/run.log" || true
  if grep -qE "must not contain duplicate matches|THROW_CHECK_LE" "$out/run.err"; then
    echo "!!! ASSERTION RED LINE HIT in $name"
  fi
  rm -rf "$dbdir"
}

for r in r1 r2 r3; do
  run_one cap50_debt_$r "$OUTC/cap50_debtfix_db" "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl"
done
echo "FIX-A REPLAYS DONE $(date +%H:%M:%S)"
