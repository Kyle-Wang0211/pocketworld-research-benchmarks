#!/usr/bin/env bash
# ============================================================================
# 一条命令:ckpt -> ETH3D office 26 帧推理 -> 官方 filter.py 融合 -> 官方 ETH3D
#          评测 -> 分区域(墙/天花板/地板/杂物)指标。输入只有 ckpt 路径。
#
#   bash eval_ckpt.sh --ckpt /path/to/x.ckpt --tag mytag [--baseline new]
#
# 全部口径逐字复刻 2026-08-24 那次三臂对比(run_20260824/REPORT.md +
# region_metric_20260824/),没有任何自造参数:
#   * 推理 run_arm.py --num_view 10 --max_w 768 --max_h 576(噪声种子默认 20260818,
#     固定噪声开启)—— 模型超参写死在 run_arm.py:53-58,与官方 test.py 的
#     casdiffmvs 分支逐字相同
#   * 融合 fuse_arm.py -> filter.py::filter_depth(3, 1.0, 0.01, [0.3,0.5,0.5],
#     "casdiffmvs", "general")
#   * 官方评测 ETH3DMultiViewEvaluation --tolerances 0.01,0.02,0.05,0.1(主表)
#     以及 0.01,0.02,0.05 + 两个 viz 输出(分区域用)
#   * 分区域 region_metrics.py 原样复用(只把模块级 TAGS 换成本次的 tag),
#     GT 侧产物(gt_merged_xyz/gt_labels/gt_labels_altwall)与 ckpt 无关,直接复用缓存
# ============================================================================
set -euo pipefail

CKPT=""; TAG=""; BASELINE="new"; WORK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --ckpt) CKPT="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --baseline) BASELINE="$2"; shift 2 ;;   # 一并出现在对比表里的已有臂,逗号分隔
    --work) WORK="$2"; shift 2 ;;
    *) echo "未知参数 $1" >&2; exit 2 ;;
  esac
done
[ -n "$CKPT" ] && [ -n "$TAG" ] || { echo "用法: bash eval_ckpt.sh --ckpt X --tag Y" >&2; exit 2; }

# 所有根路径都可用环境变量覆盖(租用机上路径不同)
A=${ETH3D_LINE:-/Users/kaidongwang/Developer/ethd3d_a_line}
REF=${ETH3D_REF:-$A/run_20260824}
TOOLS=${ARM_TOOLS:-/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/mvs_pose_ablation_2026-08-18/tools}
EVAL=$A/multi-view-evaluation/build/ETH3DMultiViewEvaluation
MLP=$A/data/office/dslr_scan_eval/scan_alignment.mlp
RM=${REGION_METRIC:-$A/region_metric_20260824}
MVS_IN=$REF/mvs_office
PACK=${PACK:-$(cd "$(dirname "$0")" && pwd)}
WORK=${WORK:-$A/eval_runs/$TAG}

for p in "$CKPT" "$EVAL" "$MLP" "$TOOLS/run_arm.py" "$TOOLS/fuse_arm.py" \
         "$RM/region_metrics.py" "$RM/cache/gt_labels.npy" \
         "$RM/cache/gt_labels_altwall.npy" "$RM/cache/gt_merged_xyz.npy"; do
  [ -e "$p" ] || { echo "[fatal] 缺少 $p" >&2; exit 1; }
done

mkdir -p "$WORK/logs" "$RM/viz" "$RM/logs"

# ---- 0. 26 帧 MVSNet 格式输入(与 ckpt 无关,已有就复用) --------------------
if [ ! -f "$MVS_IN/pair.txt" ]; then
  echo "[fatal] 缺少 $MVS_IN —— 请先按 RENTED_MACHINE_RUNBOOK.md 附录 A 重建 COLMAP 输入" >&2
  exit 1
fi
echo "[0/5] 输入复用 $MVS_IN ($(head -1 "$MVS_IN/pair.txt") 帧)"

# ---- 1. 推理 --------------------------------------------------------------
echo "[1/5] 推理 -> $WORK/out_$TAG"
${PY:-python3.11} "$TOOLS/run_arm.py" --mvs_in "$MVS_IN" --out "$WORK/out_$TAG" \
  --ckpt "$CKPT" --num_view 10 --max_w 768 --max_h 576 \
  > "$WORK/logs/run_$TAG.log" 2>&1

# ---- 2. 融合 --------------------------------------------------------------
echo "[2/5] 融合 -> $WORK/dense_$TAG.ply"
${PY:-python3.11} "$TOOLS/fuse_arm.py" --pair_folder "$MVS_IN" \
  --out_folder "$WORK/out_$TAG" --ply "$WORK/dense_$TAG.ply" \
  > "$WORK/logs/fuse_$TAG.log" 2>&1

# ---- 3. 官方评测(主表,四档容差) -----------------------------------------
echo "[3/5] 官方 ETH3D 评测(四档)"
"$EVAL" --reconstruction_ply_path "$WORK/dense_$TAG.ply" \
  --ground_truth_mlp_path "$MLP" --tolerances 0.01,0.02,0.05,0.1 \
  > "$WORK/logs/eval_$TAG.log" 2>&1
grep -E "Completenesses|Accuracies|F1-scores" "$WORK/logs/eval_$TAG.log"

# ---- 4. 官方评测(三档 + 逐点 viz,给分区域用) ------------------------------
echo "[4/5] 官方 ETH3D 评测(三档 + viz 点云)"
"$EVAL" --reconstruction_ply_path "$WORK/dense_$TAG.ply" \
  --ground_truth_mlp_path "$MLP" --tolerances 0.01,0.02,0.05 \
  --completeness_cloud_output_path "$RM/viz/comp_$TAG" \
  --accuracy_cloud_output_path "$RM/viz/acc_$TAG" \
  > "$RM/logs/eval_viz_$TAG.log" 2>&1

# ---- 5. 分区域指标 --------------------------------------------------------
echo "[5/5] 分区域指标(TAGS=$BASELINE,$TAG)"
${PY:-python3.11} "$PACK/region_metrics_tags.py" --tags "$BASELINE,$TAG" \
  --out "$WORK/region_results_$TAG.json" 2>&1 | tee "$WORK/logs/region_$TAG.log"

${PY:-python3.11} "$PACK/region_tables.py" --results "$WORK/region_results_$TAG.json" \
  --tags "$BASELINE,$TAG" --new "$TAG" | tee "$WORK/REGION_TABLES_$TAG.md"

echo
echo "[done] 产物:"
echo "  点云       $WORK/dense_$TAG.ply"
echo "  官方指标   $WORK/logs/eval_$TAG.log"
echo "  分区域 json $WORK/region_results_$TAG.json"
echo "  分区域表   $WORK/REGION_TABLES_$TAG.md"
