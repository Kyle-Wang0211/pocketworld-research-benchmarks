#!/usr/bin/env bash
# ============================================================================
# 从 casdiffmvs_mvgZeroDTU.ckpt 续训,数据 = BlendedMVG + TG 白墙子集(混合比例可调)
#
#   ./finetune_tgmix.sh calib          # 🔴 先跑:200 步定标,打印单步耗时+显存
#   ./finetune_tgmix.sh run            # 正式续训
#
# 环境变量:
#   DIFFMVS_DIR  diffmvs 仓库          (默认 ~/diffmvs)
#   MIX_ROOT     混合根目录(软链)     必填,make_mixed_list.py 的 --out_root
#   TRAINLIST    混合训练清单          必填,make_mixed_list.py 产出的 train_tgXX.txt
#   VALLIST      验证清单(纯 MVG)     必填
#   LOADCKPT     续训起点              默认 ./casdiffmvs_mvgZeroDTU.ckpt
#   OUT_ROOT     输出根                默认 ./runs_tgmix
#   TAG          本次实验名            默认由 TRAINLIST 文件名推出
#   EPOCHS       OneCycle 的总轮数     默认 4
#   BATCH        默认 4  (= 官方值)
#   NUM_WORKERS  默认 16 (prep_h100.sh 的补丁生效时才有用)
#   BLEND_CACHE  设了就走 blend_cached(mmap 预解码),否则走官方 blend
#
# 🔴 与官方 scripts/train/train_casdiffmvs.sh 的 BlendedMVS 段相比,**有意差异只有三条**:
#   1. --loadckpt 指向 mvgZeroDTU 权重(官方那里是 DTU 段的产物)
#   2. --trainlist 指向混合清单(MVG 全量 + TG 重复 R 次)
#   3. --epochs 默认 4(官方 16)—— 这是微调不是从头训
#  其余超参逐字保持官方值:trainviews/testviews=9、numdepth=384、numdepth_initial=48、
#  stage_iters 1 3 3、cost_dim_stage 4 4 4、CostNum 0 4 4、min_radius 0.125、
#  max_radius 8、hidden_dim 0 32 20、context_dim 32 32 16、unet_dim 0 16 8、
#  lr 0.001、lr_sche onecycle、conf_weight 0.05(⚠️ argparse 默认 1.0,不显式传差 20 倍)。
#  --scale 走官方 blend 段的两档课程:前半 0 0.25 0.05,后半 0 0.125 0.025。
# ============================================================================
set -euo pipefail

DIFFMVS_DIR="${DIFFMVS_DIR:-$HOME/diffmvs}"
: "${MIX_ROOT:?需要 MIX_ROOT=混合根目录}"
: "${TRAINLIST:?需要 TRAINLIST=混合训练清单}"
: "${VALLIST:?需要 VALLIST=验证清单}"
LOADCKPT="${LOADCKPT:-$PWD/casdiffmvs_mvgZeroDTU.ckpt}"
OUT_ROOT="${OUT_ROOT:-$PWD/runs_tgmix}"
EPOCHS="${EPOCHS:-4}"
BATCH="${BATCH:-4}"
NUM_WORKERS="${NUM_WORKERS:-16}"
TAG="${TAG:-$(basename "$TRAINLIST" .txt)}"

[ -f "$LOADCKPT" ] || { echo "❌ 缺 $LOADCKPT"; exit 1; }
[ -f "$TRAINLIST" ] || { echo "❌ 缺 $TRAINLIST"; exit 1; }
[ -f "$VALLIST" ]   || { echo "❌ 缺 $VALLIST"; exit 1; }

if [ -n "${BLEND_CACHE:-}" ]; then
  [ -f "$BLEND_CACHE/images.json" ] || {
    echo "❌ BLEND_CACHE=$BLEND_CACHE 里没有 images.json,先跑 predecode_blend.py"; exit 1; }
  DATASET=blend_cached
else
  DATASET=blend
  echo "⚠️ 未设 BLEND_CACHE,走原版逐样本 JPEG 解码;9 视图 × batch4 = 每批 36 次解码。"
fi

echo "数据根 : $MIX_ROOT"
echo "训练集 : $TRAINLIST ($(wc -l < "$TRAINLIST") 行 scan,含重复)"
echo "验证集 : $VALLIST ($(wc -l < "$VALLIST") 行)"
echo "起点   : $LOADCKPT"
echo "数据集实现: $DATASET   epochs=$EPOCHS  batch=$BATCH"

COMMON=(
  --mode=train --dataset="$DATASET"
  --trainpath="$MIX_ROOT" --trainlist "$TRAINLIST" --testlist "$VALLIST"
  --batch_size="$BATCH"
  --trainviews=9 --testviews=9
  --numdepth=384 --numdepth_initial=48
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4
  --min_radius 0.125 --max_radius 8
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8
  --lr 0.001 --lr_sche onecycle --conf_weight 0.05
)

run_phase() {  # run_phase <logdir> <tag> <extra args...>
  local logdir="$1"; shift
  local tag="$1"; shift
  mkdir -p "$logdir"
  echo "── $tag ──"
  NUM_WORKERS="$NUM_WORKERS" BLEND_CACHE="${BLEND_CACHE:-}" \
    python -u "$DIFFMVS_DIR/train.py" "${COMMON[@]}" \
      --logdir "$logdir" "$@" 2>&1 | tee -a "$logdir/$tag.log"
}

case "${1:-run}" in
  calib)
    # 200 步定标:不产出可用权重,只产出「单步耗时」和「显存」两个数。
    # 做法:照常起训,后台 200 秒后打一次 nvidia-smi,再由外面 Ctrl-C / timeout 掐断。
    D="$OUT_ROOT/calib_$TAG"
    mkdir -p "$D"
    ( sleep 120; echo "── nvidia-smi(训练稳定后)──"; \
      nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv ) &
    SMI=$!
    set +e
    NUM_WORKERS="$NUM_WORKERS" BLEND_CACHE="${BLEND_CACHE:-}" \
      python -u "$DIFFMVS_DIR/train.py" "${COMMON[@]}" \
        --logdir "$D" --loadckpt="$LOADCKPT" \
        --epochs="$EPOCHS" --train_epochs=1 --scale 0 0.25 0.05 \
        --summary_freq=10 --save_freq=999 2>&1 \
      | tee "$D/calib.log" \
      | awk 'NR<=400{print} NR==400{print "\n[calib] 已打印前 400 行,自行 Ctrl-C 结束"}'
    set -e
    wait $SMI 2>/dev/null || true
    echo
    echo "🔴 从 $D/calib.log 里读两个数:"
    echo "   1) 'dataset train metas:' 那一行 = 每轮样本数"
    echo "   2) 'time=' = 每 iter 秒数"
    echo "   小时数 = (样本数 / batch) * epochs * 每iter秒 / 3600"
    ;;
  run)
    D="$OUT_ROOT/$TAG"
    H=$(( EPOCHS / 2 )); [ "$H" -ge 1 ] || H=1
    run_phase "$D" p1 --loadckpt="$LOADCKPT" --epochs="$EPOCHS" \
        --train_epochs="$H" --scale 0 0.25 0.05
    run_phase "$D" p2 --resume --epochs="$EPOCHS" --scale 0 0.125 0.025
    echo "✅ 权重在 $D/model_*.ckpt"
    echo "   下一步:bash eval_ckpt.sh --ckpt <ckpt> --tag <tag>"
    ;;
  *) echo "用法: $0 calib|run"; exit 1 ;;
esac
