#!/bin/bash
# E21: live create gate (kMaxCreateReprojPx) calibration scan — audit D#5.
# build (patched copy, untracked build dir, HANDOFF-compliant) -> smoke parity
# at default 10 -> scan {2,4,6,8,10} x {cap51,cap50} r1 -> rulers.
set -u
B=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
E21=$EXP/E21_create_gate
F=$B/CMakeFiles/sfm_replay_bench_exe.dir/flags.make
DEFS=$(grep '^CXX_DEFINES' $F | sed 's/^CXX_DEFINES = //')
INCS=$(grep '^CXX_INCLUDES' $F | sed 's/^CXX_INCLUDES = //')
FLGS=$(grep '^CXX_FLAGS = ' $F | sed 's/^CXX_FLAGS = //')

echo "=== BUILD $(date +%H:%M:%S)"
cd $B
GVSRC=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor
/usr/bin/c++ $DEFS $INCS -I$GVSRC/bench $FLGS -c aether_sfm_c_e21.cc -o aether_sfm_c_e21.cc.o 2> $E21/e21_compile.err
rc=$?; [ $rc -ne 0 ] && { echo "COMPILE FAIL rc=$rc"; tail -20 $E21/e21_compile.err; exit 1; }
/usr/bin/c++ -I/opt/homebrew/include/eigen3 -I/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/include -O3 -DNDEBUG -arch arm64 \
  -Wl,-search_paths_first -Wl,-headerpad_max_install_names \
  CMakeFiles/sfm_replay_bench_exe.dir/bench/sfm_replay_bench.cc.o aether_sfm_c_e21.cc.o \
  -o sfm_replay_bench_e21_exe libglomap_core.a /opt/homebrew/lib/libceres.dylib /opt/homebrew/lib/libglog.dylib -lsqlite3 2> $E21/e21_link.err
rc=$?; [ $rc -ne 0 ] && { echo "LINK FAIL rc=$rc"; tail -20 $E21/e21_link.err; exit 1; }
EXE=$B/sfm_replay_bench_e21_exe
shasum -a 256 $EXE | tee $E21/e21_exe.sha

PROD=(AETHER_STREAM_TEMPORAL_ONLY=1 AETHER_LIVE_CAND_K_HOT=6 AETHER_TRACK_UPGRADE=1
      AETHER_ENRICH_TARGETED=1 AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4
      AETHER_GHOST_MASK=1)

run_one() {
  local cap=$1 gate=$2 dbsrc=$3 fed=$4
  local out=$E21/runs/${cap}_g${gate}
  [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log" && { echo "SKIP ${cap}_g${gate}"; return; }
  rm -rf "$out"; mkdir -p "$out/input_db"
  cp "$dbsrc" "$out/input_db/sfm_live.db"
  env "${PROD[@]}" AETHER_CREATE_REPROJ_PX=$gate \
    "$EXE" "$out/input_db/sfm_live.db" "$fed" "$out" --k=12 --keep-session-db=0 \
    > "$out/run.log" 2> "$out/run.err"
  echo "${cap}_g${gate} rc=$? $(grep '^RESULT' "$out/run.log" | grep -oE 'n_points=[0-9]+|track3plus=[0-9]+|finalize_ms=[0-9.]+' | tr '\n' ' ')"
  rm -rf "$out/input_db"
}

echo "=== SMOKE default-10 parity $(date +%H:%M:%S)"
run_one cap51 10 "$DATA/cap51/replay_database/sfm_live.db" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
np=$(grep -o 'n_points=[0-9]*' $E21/runs/cap51_g10/run.log | cut -d= -f2)
echo "smoke n_points=$np (baseline band 65,927-65,929)"
case $np in 6592[5-9]|6593[0-1]) echo "SMOKE PARITY OK";; *) echo "!! SMOKE OFF-BAND — continuing but verdict must address";; esac

echo "=== SCAN $(date +%H:%M:%S)"
for g in 2 4 6 8; do
  run_one cap51 $g "$DATA/cap51/replay_database/sfm_live.db" "$DATA/cap51/private_manifests/sfm_fed_frames.jsonl"
done
for g in 2 4 6 8 10; do
  run_one cap50 $g "$DATA/cap50/device_full_pull_2026-07-17/sfm_live.db" "$DATA/cap50/device_full_pull_2026-07-17/sfm_fed_frames.jsonl"
done
python3.11 $E21/rulers_scan.py
echo "=== E21 DONE $(date -Iseconds)"
