#!/bin/bash
# ============================================================================
# 完全版 A+B 全自动链条 —— 排在当前快档训练之后, 不抢它的 CPU
#
#   [1] 等当前 casdiff_AB 训练结束
#   [2] SimpleProc 扩到 5,189 场景 (下载 82 shard, 边转边删 tar)
#   [3] 建完全版 list (保持 33:67, 只放大规模)
#   [4] 启动完全版训练 (起点与快档【完全相同】= casdiff_B_simpleproc/model_000015.ckpt)
#
# 单变量原则: 快档 vs 完全版, 唯一变量是数据量。比例/配方/起点/nviews 全不动。
# ============================================================================
set -u
LOG=/root/full_pipeline.log
exec >> "$LOG" 2>&1
echo "=== [$(date +%H:%M)] 完全版链条启动 ==="

# ---- [1] 等当前训练结束 (判据: 真正的 train.py 进程为 0, 不用 pgrep -f 免得匹配到自己)
echo "[1/4] 等当前快档训练结束..."
while true; do
  n=$(ps -eo command | awk '/train\.py/ && /casdiff_AB/ && !/awk/' | wc -l)
  [ "$n" -eq 0 ] && break
  sleep 60
done
echo "[1/4] 快档训练已结束 $(date +%H:%M)  ckpt: $(ls /root/diffmvs/checkpoints/casdiff_AB/*.ckpt | wc -l) 个"

# ---- [2] 扩 SimpleProc 到 5,189 场景
TARGET_SCENES=5189
have=$(ls -d /root/monotrain/sp_scene_* 2>/dev/null | wc -l)
echo "[2/4] SimpleProc 扩展: 现有 $have 场景, 目标 $TARGET_SCENES"
lo=20   # shard 0-19 已用过
while [ "$have" -lt "$TARGET_SCENES" ]; do
  hi=$((lo + 10))
  echo "  -> 下载 shard $lo..$((hi-1))  $(date +%H:%M)"
  /venv/main/bin/python -u /root/sp_fetch.py $lo $hi || { echo "下载失败"; exit 1; }
  prev=$((lo-1))
  TARS=""
  [ -f /root/sp_raw/shard-$(printf %06d $prev).tar ] && TARS="/root/sp_raw/shard-$(printf %06d $prev).tar"
  for i in $(seq $lo $((hi-1))); do TARS="$TARS /root/sp_raw/shard-$(printf %06d $i).tar"; done
  /venv/main/bin/python -u /root/sp2mvsnet.py --tars $TARS --out /root/monotrain || { echo "转换失败"; exit 1; }
  # 删本批 tar, 保留最后一个供下批做跨 shard 重叠
  [ -f /root/sp_raw/shard-$(printf %06d $prev).tar ] && rm -f /root/sp_raw/shard-$(printf %06d $prev).tar
  for i in $(seq $lo $((hi-2))); do rm -f /root/sp_raw/shard-$(printf %06d $i).tar; done
  have=$(ls -d /root/monotrain/sp_scene_* 2>/dev/null | wc -l)
  lo=$hi
  echo "  -> 现有 $have 场景, df: $(df -h / | tail -1 | awk '{print $4}')"
  [ "$lo" -gt 900 ] && { echo "shard 用尽"; break; }
done
echo "[2/4] SimpleProc 扩展完成: $have 场景 $(date +%H:%M)"

# ---- [3] 建完全版 list
echo "[3/4] 建完全版 list"
/venv/main/bin/python -u /root/build_full_lists.py || { echo "建 list 失败"; exit 1; }

# ---- [4] 启动完全版训练
echo "[4/4] 启动完全版训练 $(date +%H:%M)"
/root/train_AB_full.sh
echo "=== [$(date +%H:%M)] 完全版链条结束 ==="
