#!/usr/bin/env bash
set -euo pipefail

PY="${PY:-/venv/main/bin/python}"
: "${DIFFMVS_DIR:?set DIFFMVS_DIR to the frozen official DiffMVS checkout}"
: "${BASE_CKPT:?set BASE_CKPT to the frozen starting checkpoint}"
: "${GENERATED_ROOT:?set GENERATED_ROOT to generate_balanced_tg.py output}"
: "${OUT_ROOT:?set OUT_ROOT to the experiment output directory}"

BATCH=4
SEED=20260825
TRAIN_PY="$DIFFMVS_DIR/train.py"
FORMAL_DIR="$OUT_ROOT/formal"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

fail() {
  echo "fatal: $*" >&2
  exit 1
}

require_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

require_dataset() {
  local dataset_dir="$1"
  local expected_mvg="$2"
  local expected_tg="$3"
  require_file "$dataset_dir/train.txt"
  require_file "$dataset_dir/val.txt"
  require_file "$dataset_dir/manifest.json"
  [ -d "$dataset_dir/root" ] || fail "missing directory: $dataset_dir/root"
  "$PY" - "$dataset_dir" "$expected_mvg" "$expected_tg" "$SCRIPT_DIR/generate_balanced_tg.py" <<'PY'
import hashlib, json, pathlib, sys
dataset = pathlib.Path(sys.argv[1])
expected_mvg, expected_tg = int(sys.argv[2]), int(sys.argv[3])
generator = pathlib.Path(sys.argv[4])
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((dataset / "manifest.json").read_text())
expected_counts = {"mvg": expected_mvg, "tg": expected_tg, "total": expected_mvg + expected_tg}
if manifest.get("counts") != expected_counts:
    raise SystemExit(f"manifest counts mismatch: {manifest.get('counts')} != {expected_counts}")
if manifest.get("generator_sha256") != sha(generator):
    raise SystemExit("generator hash mismatch")
artifacts = manifest.get("artifact_sha256", {})
if not artifacts:
    raise SystemExit("manifest artifact hashes missing")
for relative, expected in artifacts.items():
    path = dataset / relative
    if not path.is_file() or sha(path) != expected:
        raise SystemExit(f"artifact hash mismatch: {relative}")
PY
}

print_command() {
  local label="$1"
  shift
  printf '%s' "$label"
  printf ' %q' "$@"
  printf '\n'
}

run_logged() {
  local log="$1"
  shift
  "$@" 2>&1 | tee "$log"
}

COMMON=(
  "$PY" -u "$TRAIN_PY"
  --dataset=blend --batch_size="$BATCH"
  --trainviews=9 --testviews=9
  --numdepth=384 --numdepth_initial=48
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4
  --min_radius=0.125 --max_radius=8
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8
  --conf_weight=0.05 --seed="$SEED"
  --lr=0.0002 --lr_sche=mslr --lrepochs=1000:2
)

require_file "$TRAIN_PY"
require_file "$BASE_CKPT"

case "${1:-}" in
  calib)
    [ "$#" -eq 1 ] || fail "usage: $0 calib"
    dataset_dir="$GENERATED_ROOT/calibration"
    require_dataset "$dataset_dir" 400 400
    logdir="$OUT_ROOT/calibration"
    mkdir -p "$logdir"
    if find "$logdir" -maxdepth 1 -type f -name 'model_*.ckpt' -print -quit | grep -q .; then
      fail "calibration checkpoint is forbidden; remove the existing model_*.ckpt before calibration"
    fi
    train_cmd=(
      "${COMMON[@]}" --mode=train
      --trainpath="$dataset_dir/root" --testpath="$dataset_dir/root"
      --trainlist="$dataset_dir/train.txt" --testlist="$dataset_dir/val.txt"
      --logdir="$logdir" --loadckpt="$BASE_CKPT"
      --epochs=1 --train_epochs=1 --save_freq=999
      --scale 0 0.25 0.05
    )
    echo "[calib] 800 metas / batch 4 = 200 steps"
    print_command "TRAIN_CMD" "${train_cmd[@]}"
    if [ "${DRY_RUN:-0}" = 1 ]; then
      exit 0
    fi
    run_logged "$logdir/calibration.log" "${train_cmd[@]}"
    if find "$logdir" -maxdepth 1 -type f -name 'model_*.ckpt' -print -quit | grep -q .; then
      fail "calibration produced a forbidden model_*.ckpt"
    fi
    steps=$(grep -Ec 'Epoch 0/1, Iter [0-9]+/200,' "$logdir/calibration.log" || true)
    [ "$steps" -eq 200 ] || fail "calibration logged $steps training steps, expected exactly 200"
    echo "CALIBRATION_COMPLETE steps=200 checkpoint_policy=none log=$logdir/calibration.log"
    ;;

  run-epoch)
    [ "$#" -eq 2 ] || fail "usage: $0 run-epoch N (N must be 1..10)"
    epoch="$2"
    case "$epoch" in
      1|2|3|4|5|6|7|8|9|10) ;;
      *) fail "epoch must be an integer from 1 through 10" ;;
    esac
    printf -v epoch_tag '%02d' "$epoch"
    dataset_dir="$GENERATED_ROOT/epoch_$epoch_tag"
    require_dataset "$dataset_dir" 1774 1774
    mkdir -p "$FORMAL_DIR"
    checkpoint_index=$((epoch - 1))
    printf -v checkpoint_name 'model_%06d.ckpt' "$checkpoint_index"
    checkpoint="$FORMAL_DIR/$checkpoint_name"
    if [ "$epoch" -le 5 ]; then
      train_scale=(0 0.25 0.05)
    else
      train_scale=(0 0.125 0.025)
    fi
    if [ "$epoch" -eq 1 ]; then
      continuation=(--loadckpt="$BASE_CKPT")
    else
      previous_index=$((epoch - 2))
      printf -v previous_name 'model_%06d.ckpt' "$previous_index"
      previous="$FORMAL_DIR/$previous_name"
      if [ "${DRY_RUN:-0}" != 1 ]; then
        require_file "$previous"
        checkpoint_count=0
        for candidate in "$FORMAL_DIR"/*.ckpt; do
          [ -e "$candidate" ] || continue
          checkpoint_count=$((checkpoint_count + 1))
          case "$(basename "$candidate")" in
            model_[0-9][0-9][0-9][0-9][0-9][0-9].ckpt) ;;
            *) fail "unexpected checkpoint would affect official resume: $candidate" ;;
          esac
        done
        [ "$checkpoint_count" -eq "$((epoch - 1))" ] || \
          fail "expected $((epoch - 1)) checkpoints before epoch $epoch, found $checkpoint_count"
        expected_index=0
        while [ "$expected_index" -le "$previous_index" ]; do
          printf -v expected_name 'model_%06d.ckpt' "$expected_index"
          require_file "$FORMAL_DIR/$expected_name"
          expected_index=$((expected_index + 1))
        done
      fi
      continuation=(--resume)
    fi
    if [ "${DRY_RUN:-0}" != 1 ] && [ -e "$checkpoint" ]; then
      fail "target checkpoint already exists: $checkpoint"
    fi
    train_log="$FORMAL_DIR/train_epoch_$epoch_tag.log"
    val_log="$FORMAL_DIR/val_epoch_$epoch_tag.log"
    train_cmd=(
      "${COMMON[@]}" --mode=train
      --trainpath="$dataset_dir/root" --testpath="$dataset_dir/root"
      --trainlist="$dataset_dir/train.txt" --testlist="$dataset_dir/val.txt"
      --logdir="$FORMAL_DIR" "${continuation[@]}"
      --epochs=10 --train_epochs="$epoch" --save_freq=1
      --scale "${train_scale[@]}"
    )
    val_cmd=(
      "${COMMON[@]}" --mode=test
      --trainpath="$dataset_dir/root" --testpath="$dataset_dir/root"
      --trainlist="$dataset_dir/train.txt" --testlist="$dataset_dir/val.txt"
      --logdir="$FORMAL_DIR" --loadckpt="$checkpoint"
      --epochs=10 --scale 0 0.125 0.025
    )
    print_command "TRAIN_CMD" "${train_cmd[@]}"
    echo "expected checkpoint: $checkpoint"
    print_command "VAL_CMD" "${val_cmd[@]}"
    echo "validation log: $val_log"
    if [ "${DRY_RUN:-0}" = 1 ]; then
      exit 0
    fi
    run_logged "$train_log" "${train_cmd[@]}"
    require_file "$checkpoint"
    grep -Eq 'lr[ =]+0\.000200([,[:space:]]|$)' "$train_log" || \
      fail "training log does not contain lr 0.000200: $train_log"
    {
      echo "BALANCED_TG_VAL epoch=$epoch checkpoint=$checkpoint seed=$SEED scale=0,0.125,0.025"
      "${val_cmd[@]}"
    } 2>&1 | tee "$val_log"
    echo "EPOCH_COMPLETE epoch=$epoch checkpoint=$checkpoint train_log=$train_log val_log=$val_log"
    ;;

  *)
    fail "usage: $0 calib | $0 run-epoch N"
    ;;
esac
