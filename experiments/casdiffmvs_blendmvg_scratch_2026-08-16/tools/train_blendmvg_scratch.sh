#!/usr/bin/env bash
# CasDiffMVS 去 DTU 血统:两段式训练
#
#   段① 配置筛选  在 **BlendedMVS(106 场景)** 上从头训 A/B/C/D 四配置
#                 —— 单变量:只变"有没有 DTU 预训练",数据集与官方 blend 段保持一致,
#                    所以拿到的数字能直接和官方权重对比
#   段② 最终训练  赢家权重 → **微调全量 BlendedMVG**
#                 —— 与官方新权重结构平行(官方是 DTU→微调 MVG,我们是 MVS→微调 MVG),
#                    是微调不是从头训,所以便宜
#
# 两份数据都是 CC BY 4.0 ⇒ 全程零 DTU,血统干净。
#
# 用法:
#   ./train_blendmvg_scratch.sh pilot                # 🔴 先跑:量 it/s 与显存
#   ./train_blendmvg_scratch.sh A B C D              # 段①(默认 TIER=mvs)
#   TIER=mvg ./train_blendmvg_scratch.sh finetune:B  # 段②:拿 B 的赢家微调 MVG
#
# 环境变量:
#   DIFFMVS_DIR   diffmvs 仓库(默认 ~/diffmvs)
#   TIER          mvs(默认,段①)| mvg(段②)
#   MVS_ROOT      BlendedMVS 根目录          (TIER=mvs 必须)
#   MVG_ROOT      BlendedMVG 根目录          (TIER=mvg 必须)
#   LISTS_DIR     make_blendmvg_list.py 产出 (TIER=mvg 必须)
#   OUT_ROOT      输出根(默认 ./runs)
#   NUM_WORKERS   dataloader 进程数(默认 16,见 prep_h100.sh 的补丁)
#   BATCH         batch(默认 4 = 官方值;⚠️ 改了就不能和历史数字比)
#
# ⚠️ 与官方 scripts/train/train_casdiffmvs.sh 的**有意差异只有三条**:
#      1. 段①不传 --loadckpt ⇒ 从头训(train.py:45 默认 None、:338 是 elif)
#      2. 段②的 --trainlist 指向自建 BlendedMVG 清单(仓库只有 BlendedMVS 的)
#      3. 轮数与 --scale 课程按配置变化
#    其余超参逐字保持官方值 —— 动了就不能和已有的 138 帧数字比。
set -euo pipefail

DIFFMVS_DIR="${DIFFMVS_DIR:-$HOME/diffmvs}"
OUT_ROOT="${OUT_ROOT:-$PWD/runs}"
NUM_WORKERS="${NUM_WORKERS:-16}"
BATCH="${BATCH:-4}"
TIER="${TIER:-mvs}"

case "$TIER" in
  mvs)
    : "${MVS_ROOT:?TIER=mvs 需要 MVS_ROOT=BlendedMVS 根目录}"
    DATA_ROOT="$MVS_ROOT"
    # 段①直接用仓库自带清单 —— 106 场景,与官方 blend 段完全同一份数据
    TRAINLIST="$DIFFMVS_DIR/lists/blend/train.txt"
    VALLIST="$DIFFMVS_DIR/lists/blend/val.txt"
    ;;
  mvg)
    : "${MVG_ROOT:?TIER=mvg 需要 MVG_ROOT=BlendedMVG 根目录}"
    : "${LISTS_DIR:?TIER=mvg 需要 LISTS_DIR=make_blendmvg_list.py 的输出目录}"
    DATA_ROOT="$MVG_ROOT"
    TRAINLIST="$LISTS_DIR/train.txt"
    VALLIST="$LISTS_DIR/val.txt"
    ;;
  *) echo "TIER 只能是 mvs 或 mvg,收到 $TIER"; exit 1 ;;
esac
[ -f "$TRAINLIST" ] || { echo "❌ 缺 $TRAINLIST"; exit 1; }
echo "TIER=$TIER  数据=$DATA_ROOT  清单=$TRAINLIST ($(wc -l < "$TRAINLIST") 场景)"

# ── 数据集实现:设了 BLEND_CACHE 就走 mmap 预解码版 ────────────────────
#    blend_cached 只把 read_img/read_depth 换成读 mmap,其余逐字继承原版
#    ⇒ 喂给模型的张量**逐位相同**(已实测:test/train 两模式、num_workers 0/2/4 全等)
if [ -n "${BLEND_CACHE:-}" ]; then
  [ -f "$BLEND_CACHE/images.json" ] || {
    echo "❌ BLEND_CACHE=$BLEND_CACHE 里没有 images.json,先跑 predecode_blend.py"; exit 1; }
  DATASET=blend_cached
  echo "数据集: blend_cached(mmap 缓存 $BLEND_CACHE)—— CPU 解码已消除"
else
  DATASET=blend
  echo "⚠️ 未设 BLEND_CACHE,走原版逐样本 JPEG 解码。"
  echo "   9 视图 × batch4 = 每批 36 次解码,租来的机器 vCPU 通常不够,GPU 会空转。"
  echo "   强烈建议先跑 predecode_blend.py。"
fi

# ── 逐字来自官方 train_casdiffmvs.sh 的 BlendedMVS 段,不要改 ──────────
COMMON=(
  --mode=train --dataset="$DATASET"
  --trainpath="$DATA_ROOT" --trainlist "$TRAINLIST" --testlist "$VALLIST"
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
  NUM_WORKERS="$NUM_WORKERS" BLEND_CACHE="${BLEND_CACHE:-}" \
    python -u "$DIFFMVS_DIR/train.py" \
      "${COMMON[@]}" --logdir "$logdir" "$@" 2>&1 | tee -a "$logdir/$tag.log"
}

# ══════════════════════════════════════════════════════════════════════
# pilot:🔴 上机后第一件事。不产出可用权重,只产出两个数字。
#   MVS 的显存大头是 cost volume 不是权重(模型 state_dict 才 1.385M 浮点)⇒
#   **按参数量估显存一定错**,必须实测才知道能并发几个。
#   同时 `time=` 给出每 iter 秒数 ⇒ 所有时长估算立刻换成真数。
# ══════════════════════════════════════════════════════════════════════
cfg_pilot() {
  local d="$OUT_ROOT/pilot_$TIER"
  ( sleep 90; echo "── nvidia-smi(训练稳定后)──"; nvidia-smi \
      --query-gpu=memory.used,memory.total,utilization.gpu --format=csv ) &
  run_phase "$d" pilot --epochs=16 --train_epochs=1 --lr=0.001 \
      --scale 0 0.25 0.05 --save_freq=1 --summary_freq=10
  wait
  cat <<'TIP'

🔴 从上面读两个数,别再用任何估算:
   1) 日志里的 time=  ⇒ 每 iter 秒数
      小时数 =(样本数 ÷ batch)× 轮数 × 每iter秒 ÷ 3600
      样本数 = 日志开头 "dataset train metas:" 那一行
   2) nvidia-smi 的 memory.used ⇒ 单进程占用
      并发数 = 显存总量 × 0.85 ÷ 单进程占用
TIP
}

# ══════════════════════════════════════════════════════════════════════
# 段① 四配置。设计原则:每个配置消灭一个具体的不确定性,不是随机撒点。
# ══════════════════════════════════════════════════════════════════════

# A 基准:官方 blend 段配方原样搬到从头训。对照组。
#   16 轮 OneCycle、第 8 轮切 scale —— 与官方结构一致
#   (官方那两次 train.py 调用其实是**同一条 16 轮 OneCycle**,
#    劈开只为中途换 --scale;见 train.py:371-372)
cfg_A() {
  local d="$OUT_ROOT/${TIER}_A_baseline"
  run_phase "$d" A_p1 --epochs=16 --train_epochs=8 --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" A_p2 --epochs=16 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# B 全课程:把 DTU 段的噪声课程补回来。★ 我最看好这个。
#   官方 scale 课程 0.5→0.25→0.125,其中 **0.5 那档只在 DTU 段出现**。
#   丢掉 DTU = 跳过课程第一档 ⇒ B 是唯一在结构上补偿了这一点的配置。
cfg_B() {
  local d="$OUT_ROOT/${TIER}_B_curriculum"
  run_phase "$d" B_p1 --epochs=24 --train_epochs=8  --lr=0.001 --scale 0 0.5   0.1
  run_phase "$d" B_p2 --epochs=24 --train_epochs=16 --resume --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" B_p3 --epochs=24 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# C 长训:验证「从头训只是需要更多轮」这个假设。
cfg_C() {
  local d="$OUT_ROOT/${TIER}_C_long"
  run_phase "$d" C_p1 --epochs=32 --train_epochs=16 --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" C_p2 --epochs=32 --resume          --lr=0.001 --scale 0 0.125 0.025
}

# D 低 LR:验证「从头训时 OneCycle 峰值 1e-3 过高会发散」这个假设。
#   官方的 1e-3 是在**已有 DTU 初始化**的前提下调的。
cfg_D() {
  local d="$OUT_ROOT/${TIER}_D_lowlr"
  run_phase "$d" D_p1 --epochs=24 --train_epochs=12 --lr=0.0005 --scale 0 0.25  0.05
  run_phase "$d" D_p2 --epochs=24 --resume           --lr=0.0005 --scale 0 0.125 0.025
}

# ══════════════════════════════════════════════════════════════════════
# 段② 微调全量 BlendedMVG
#   结构与官方新权重平行:官方 DTU→微调 MVG,我们 BlendedMVS→微调 MVG。
#   官方原话:改用 BlendedMVG 微调「without changing other hyper-parameters」
#   ⇒ 这里就用官方 blend 段的末档参数,不另外发明。
#   ⚠️ 必须 TIER=mvg 跑。
# ══════════════════════════════════════════════════════════════════════
cfg_finetune() {   # $1 = 赢家配置名(A/B/C/D)
  local win="$1"
  [ "$TIER" = "mvg" ] || { echo "❌ finetune 必须 TIER=mvg"; exit 1; }
  local src; src=$(ls -1 "$OUT_ROOT/mvs_${win}"*/model_*.ckpt 2>/dev/null | sort | tail -1)
  [ -n "$src" ] || { echo "❌ 找不到段① $win 的权重(先跑段①)"; exit 1; }
  echo "微调起点: $src"
  local d="$OUT_ROOT/mvg_finetune_${win}"
  run_phase "$d" ft_p1 --epochs=16 --train_epochs=8 --loadckpt="$src" \
      --lr=0.001 --scale 0 0.25  0.05
  run_phase "$d" ft_p2 --epochs=16 --resume \
      --lr=0.001 --scale 0 0.125 0.025
}

[ $# -ge 1 ] || { echo "用法: $0 pilot|A|B|C|D|finetune:<配置> [更多...]"; exit 1; }

pids=()
for c in "$@"; do
  case "$c" in
    pilot)        cfg_pilot ;;                    # pilot 独占,不并发
    finetune:*)   cfg_finetune "${c#finetune:}" ;;  # 段②单跑
    A|B|C|D)      cfg_"$c" & pids+=("$!") ;;
    *) echo "未知参数 $c"; exit 1 ;;
  esac
done
for p in "${pids[@]:-}"; do [ -n "$p" ] && wait "$p" || true; done
echo "✅ 结束。逐个 ckpt 接对比台:python3 install_new_ckpt.py <ckpt> --dom <名字>"
