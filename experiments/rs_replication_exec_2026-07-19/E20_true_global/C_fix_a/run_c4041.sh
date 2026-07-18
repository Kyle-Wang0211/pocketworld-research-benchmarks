#!/bin/bash
# E3 on cap40/41, take 2 — self-consistent replay world (first attempt INVALID:
# E4 legacy replay planes sit in a different frame, tens of meters off device gauge).
# Recipe = cap50_fixA pipeline: E12 exe replay (priors, device-ish gauge) ->
# colorize -> meta from solved poses -> ghost plane from the replay's own
# production-recipe arbitration -> fingerprints/trails/e3 (python3.11).
set -u
PY=python3.11
EXP=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19
DATA=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures
C=$EXP/E20_true_global/C_fix_a
E3D=$EXP/E3_birth_discipline
TF=$EXP/TRAILS_forensics
EXE=/Users/kaidongwang/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714/aether_cpp/third_party/glomap_vendor/build-host-e12-stage2/sfm_replay_bench_exe
EXPECTED_SHA=2e03c66b50e1255692be2e47d313a079a313571fef1c4a9d5ca7e94512eb1c38
got=$(shasum -a 256 "$EXE" | awk '{print $1}')
[ "$got" = "$EXPECTED_SHA" ] || { echo "EXE SHA MISMATCH: $got"; exit 1; }
PROD_ENV=(AETHER_STREAM_TEMPORAL_ONLY=1 AETHER_LIVE_CAND_K_HOT=6
          AETHER_TRACK_UPGRADE=1 AETHER_ENRICH_TARGETED=1
          AETHER_ENRICH_PAIR_CAP=300 AETHER_STAGE1_ROUNDS_CAP=4
          AETHER_GHOST_MASK=1)

echo "=== C4041 START $(date -Iseconds)"
for cap in cap40 cap41; do
  OK=1
  case $cap in
    cap40) DB_DIR=$DATA/cap40/device_full_pull_2026-07-17 ;;
    cap41) DB_DIR=$DATA/cap41/device_db_pull_2026-07-17 ;;
  esac
  FED_F=$DB_DIR/sfm_fed_frames.jsonl
  PHO_D=$DB_DIR/photos_highres
  out=$E3D/replays/${cap}_base_r1
  if [ -f "$out/run.log" ] && grep -q "^RESULT" "$out/run.log"; then
    echo "=== SKIP replay $cap (done)"
  else
    rm -rf "$out"; mkdir -p "$out/input_db"
    cp "$DB_DIR/sfm_live.db" "$out/input_db/"
    for ext in -wal -shm; do
      [ -f "$DB_DIR/sfm_live.db$ext" ] && cp "$DB_DIR/sfm_live.db$ext" "$out/input_db/"
    done
    echo "=== REPLAY $cap $(date +%H:%M:%S)"
    /usr/bin/time -l env "${PROD_ENV[@]}" \
      "$EXE" "$out/input_db/sfm_live.db" "$FED_F" "$out" --k=12 --keep-session-db=0 \
      > "$out/run.log" 2> "$out/run.err"
    rc=$?
    echo "replay rc=$rc"; grep -E "^RESULT" "$out/run.log" || true
    [ $rc -ne 0 ] && OK=0
    rm -rf "$out/input_db"
  fi
  if [ $OK -eq 1 ]; then
    $PY $EXP/E20_true_global/A_new_matching/colorize_replay.py \
      "$out" "$FED_F" "$PHO_D" "$out/replay_finalize_rgb.ply" || OK=0
  fi
  if [ $OK -eq 1 ]; then
    ind=$E3D/${cap}_inputs
    $PY $C/make_meta2.py "$out/solved_poses.csv" "$ind/sfm_sparse_meta.json" || OK=0
    ln -sf "$DB_DIR/sfm_live.db" "$ind/sfm_live.db"
    ln -sf "$out/replay_finalize_rgb.ply" "$ind/sfm_sparse.ply"
    ln -sf "$out/ghost_mask.json" "$ind/ghost_mask.json"
  fi
  if [ $OK -eq 1 ]; then
    $PY $TF/compute_fingerprints.py $cap && $PY $TF/detect_trails.py $cap && \
    $PY $E3D/e3_birth_discipline.py $cap || OK=0
  fi
  echo "=== $cap done ok=$OK $(date +%H:%M:%S)"
done
echo "=== C4041 DONE $(date -Iseconds)"
