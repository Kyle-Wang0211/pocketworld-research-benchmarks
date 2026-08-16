#!/usr/bin/env bash
# CasDiffMVS 从头训 BlendedMVG —— 四配置 + 试跑
#
# 用法:
#   ./train_blendmvg_scratch.sh pilot          # 🔴 先跑这个:1 轮,量 it/s 与显存
#   ./train_blendmvg_scratch.sh A              # 单个配置
#   ./train_blendmvg_scratch.sh A B C D        # 并发铺(按 pilot 量到的显存决定几个)
#
# 环境变量:
#   DIFFMVS_DIR   diffmvs 仓库路径(默认 ~/diffmvs)
#   MVG_ROOT      BlendedMVG 根目录            (必须)
#   LISTS_DIR     make_blendmvg_list.py 的产出 (必须)
#   OUT_ROOT      输出根目录(默认 ./runs)
#   NUM_WORKERS   dataloader 进程数(默认 16;见 prep_h100.sh 的补丁)
#   BATCH         batch size(默认 4 = 官方值,⚠️ 改了就不能和历史数字比)
#
# ⚠️ 与官方 scripts/train/train_casdiffmvs.sh 的**唯一有意差异**是:
#      1. 不传 --loadckpt  ⇒ 从头训(train.py:45 默认 None、:338 是 elif)
#      2. --dataset=blend 但 --trainlist 指向自建的 BlendedMVG 清单
#      3. 轮次与 --scale 课程按配置变化(见 README §3)
#    其余超参逐字保持官方值 —— 动了就不能和已有的 138 帧数字比。
set -euo pipefail

DIFFMVS_DIR="${DIFFMVS_DIR:-$HOME/diffmvs}"
OUT_ROOT="${OUT_ROOT:-$PWD/runs}"
NUM_WORKERS="${NUM_WORKERS:-16}"
BATCH="${BATCH:-4}"
: "${MVG_ROOT:?请设 MVG_ROOT=BlendedMVG 根目录}"
: "${LISTS_DIR:?请设 LISTS_DIR=make_blendmvg_list.py 的输出目录}"

TRAINLIST="$LISTS_DIR/train.txt"
VALLIST="$LISTS_DIR/val.txt"
[ -f "$TRAINLIST" ] || { echo "❌ 缺 $TRAINLIST,先跑 make_blendmvg_list.py"; exit 1; }

# ── 逐字来自官方 train_casdiffmvs.sh 的 BlendedMVS 段,不要改 ──────────
COMMON=(
  --mode=train --dataset=blend
  --trainpath="$MVG_ROOT" --trainlist "$TRAINLIST" --testlist "$VALLIST"
  --batch_size="$BATCH"
  --trainviews=9 --testviews=9
  --numdepth=384 --numdepth_initial=48
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4
  --min_radius 0.125 --max_radius 8
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8
  --lr_sche onecycle
  --conf_weight 0.05     # ⚠️ argparse 默认是 1.0(train.py:83),不显式传会差 20 倍
)

run_phase() {   # run_phase <logdir> <日志名> <参数...>
  local logdir="$1"; shift
  local tag="$1"; shift
  mkdir -p "$logdir"
  echo "── $tag ──"
  NUM_WORKERS="$NUM_WORKERS" python -u "$DIFFMVS_DIR/train.py" \
      "${COMMON[@]}" --logdir "$logdir" "$@" 2>&1 | tee -a "$logdir/$tag.log"
}

# ══════════════════════════════════════════════════════════════════════
# pilot:🔴 上机后第一件事。不产出可用权重,只产出两个数字。
#   MVS 的显存大头是 cost volume 不是权重(模型仅 0.925M 参数)⇒
#   **按参数量估显存一定错**,必须实测才知道能并发几个。
# ══════════════════════════════════════════════════════════════════════
cfg_pilot() {
  local d="$OUT_ROOT/pilot"
  ( sleep 90; echo "── nvidia-smi(训练稳定后)──"; nvidia-smi \
      --query-gpu=memory.used,memory.total,utilization.gpu --format=csv ) &
  run_phase "$d" pilot --epochs=16 --train_epochs=1 --lr=0.001 \
      --scale 0 0.25 0.05 --save_freq=1 --summary_freq=10
  wait
  echo
  echo "🔴 从上面读两个数再决定并发数:"
  echo "   1) 每 iter 耗时(日志里的 time=)⇒ 真实总时长"
  echo "   2) nvidia-smi 的 memory.used  ⇒ 80GB / 单进程占用 = 能并发几个(留 15% 余量)"
}

# ══════════════════════════════════════════════════════════════════════
# A 基准:官方 BlendedMVS 段配方原样搬到从头训。对照组。
#   16 轮 OneCycle,第 8 轮切 scale —— 与官方结构一致
#   (官方那两次调用其实是**同一条 16 轮 OneCycle**,劈开只为换 scale)
# ══════════════════════════════════════════════════════════════════════
cfg_A() {
  local d="$OUT_ROOT/A_baseline"
  run_phase "$d" A_p1 --epochs=16 --train_epochs=8 --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" A_p2 --epochs=16 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# ══════════════════════════════════════════════════════════════════════
# B 全课程:把 DTU 段的噪声课程在 BlendedMVG 上补回来。
#   官方 scale 课程是 0.5→0.25→0.125,其中 0.5 那档只在 DTU 段出现。
#   丢掉 DTU = 跳过课程第一档 ⇒ B 是唯一在结构上补偿了这一点的配置。
#   ★ 我最看好这个。
# ══════════════════════════════════════════════════════════════════════
cfg_B() {
  local d="$OUT_ROOT/B_curriculum"
  run_phase "$d" B_p1 --epochs=24 --train_epochs=8  --lr=0.001 --scale 0 0.5   0.1
  run_phase "$d" B_p2 --epochs=24 --train_epochs=16 --resume --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" B_p3 --epochs=24 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# ══════════════════════════════════════════════════════════════════════
# C 长训:验证「从头训只是需要更多轮」这个假设。
# ══════════════════════════════════════════════════════════════════════
cfg_C() {
  local d="$OUT_ROOT/C_long"
  run_phase "$d" C_p1 --epochs=32 --train_epochs=16 --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" C_p2 --epochs=32 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# ══════════════════════════════════════════════════════════════════════
# D 低 LR:验证「从头训时 OneCycle 峰值 1e-3 过高会发散」这个假设。
#   官方 1e-3 是在**已有 DTU 初始化**的前提下调的。
# ══════════════════════════════════════════════════════════════════════
cfg_D() {
  local d="$OUT_ROOT/D_lowlr"
  run_phase "$d" D_p1 --epochs=24 --train_epochs=12 --lr=0.0005 --scale 0 0.25  0.05
  run_phase "$d" D_p2 --epochs=24 --resume           --lr=0.0005 --scale 0 0.125 0.025
}

[ $# -ge 1 ] || { echo "用法: $0 pilot|A|B|C|D [更多配置...]"; exit 1; }

pids=()
for c in "$@"; do
  case "$c" in
    pilot) cfg_pilot ;;                      # pilot 永远独占,不并发
    A|B|C|D) cfg_"$c" & pids+=("$!") ;;
    *) echo "未知配置 $c"; exit 1 ;;
  esac
done
for p in "${pids[@]:-}"; do [ -n "$p" ] && wait "$p" || true; done
echo "✅ 全部结束。逐个 ckpt 接对比台:tools/eval_new_ckpt.sh"
