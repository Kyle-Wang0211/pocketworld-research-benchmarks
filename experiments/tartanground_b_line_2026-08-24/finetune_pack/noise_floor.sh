#!/usr/bin/env bash
# 量这条验收链的**复跑噪声地板**:同一个 ckpt 跑 N 次全链,报每个指标的极差。
#
#   bash noise_floor.sh --ckpt X --tag base --n 3
#
# 为什么必须先跑这个(2026-08-24 本机实测):
#   同 ckpt / 同输入 / 同固定噪声(seed=20260818+帧号)/ 同机器,三次运行的
#   融合点云字节数 46,295,596 / 45,865,591 / 48,280,981,官方 acc@1cm
#   0.741918 / 0.721109 / 0.731972 —— **极差 2.08pp**。
#   ⇒ 任何小于噪声地板的"提升"都不是提升。先量地板,再谈判决。
#   ⚠️ 这个地板是 MPS 上量的,租用机是 CUDA,必须**在租用机上重量一遍**。
set -euo pipefail

CKPT=""; TAG="base"; N=3
while [ $# -gt 0 ]; do
  case "$1" in
    --ckpt) CKPT="$2"; shift 2 ;;
    --tag)  TAG="$2";  shift 2 ;;
    --n)    N="$2";    shift 2 ;;
    *) echo "未知参数 $1" >&2; exit 2 ;;
  esac
done
[ -n "$CKPT" ] || { echo "用法: bash noise_floor.sh --ckpt X [--tag base] [--n 3]" >&2; exit 2; }

A=${ETH3D_LINE:-/Users/kaidongwang/Developer/ethd3d_a_line}
T=${ARM_TOOLS:-/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/mvs_pose_ablation_2026-08-18/tools}
EVAL=$A/multi-view-evaluation/build/ETH3DMultiViewEvaluation
MLP=$A/data/office/dslr_scan_eval/scan_alignment.mlp
MVS_IN=${MVS_IN:-$A/run_20260824/mvs_office}
OUT=$A/eval_runs/noisefloor_$TAG
mkdir -p "$OUT/logs"

for i in $(seq 1 "$N"); do
  r="${TAG}_r$i"
  echo "── 第 $i/$N 次 ──"
  ${PY:-python3.11} "$T/run_arm.py" --mvs_in "$MVS_IN" --out "$OUT/out_$r" --ckpt "$CKPT" \
    --num_view 10 --max_w 768 --max_h 576 > "$OUT/logs/run_$r.log" 2>&1
  ${PY:-python3.11} "$T/fuse_arm.py" --pair_folder "$MVS_IN" --out_folder "$OUT/out_$r" \
    --ply "$OUT/dense_$r.ply" > "$OUT/logs/fuse_$r.log" 2>&1
  "$EVAL" --reconstruction_ply_path "$OUT/dense_$r.ply" --ground_truth_mlp_path "$MLP" \
    --tolerances 0.01,0.02,0.05,0.1 > "$OUT/logs/eval_$r.log" 2>&1
  echo "  ply=$(stat -f%z "$OUT/dense_$r.ply" 2>/dev/null || stat -c%s "$OUT/dense_$r.ply")"
  grep -E "Completenesses|Accuracies|F1-scores" "$OUT/logs/eval_$r.log"
done

${PY:-python3.11} - "$OUT" "$TAG" "$N" <<'PY'
import re, sys, os, json
out, tag, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
keys = ("Completenesses", "Accuracies", "F1-scores")
runs = []
for i in range(1, n + 1):
    txt = open(f"{out}/logs/eval_{tag}_r{i}.log").read()
    runs.append({k: [float(x) for x in re.search(rf"{k}: (.*)", txt).group(1).split()]
                 for k in keys})
tols = [0.01, 0.02, 0.05, 0.1]
print("\n=== 复跑噪声地板(同 ckpt %d 次)===" % n)
print("| 指标 | 容差 | min | max | 极差(pp) |")
print("|---|---|---|---|---|")
res = {}
for k in keys:
    for j, t in enumerate(tols):
        v = [r[k][j] for r in runs]
        print(f"| {k} | {t*100:.0f}cm | {min(v):.6f} | {max(v):.6f} | {(max(v)-min(v))*100:.2f} |")
        res[f"{k}@{t}"] = {"min": min(v), "max": max(v), "spread_pp": (max(v)-min(v))*100}
sizes = [os.path.getsize(f"{out}/dense_{tag}_r{i}.ply") for i in range(1, n+1)]
res["ply_bytes"] = sizes
print("\nply 字节: %s(极差 %.2f%%)" % (sizes, (max(sizes)-min(sizes))/min(sizes)*100))
json.dump(res, open(f"{out}/noise_floor.json", "w"), indent=2)
print("-> %s/noise_floor.json" % out)
PY
