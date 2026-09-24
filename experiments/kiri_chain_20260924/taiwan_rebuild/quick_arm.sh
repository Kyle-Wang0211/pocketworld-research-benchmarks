#!/bin/bash
# 唯一省略: infer_arm.sh 自带的 thres=2 融合(用不上),深度图满 132 张即终止该进程。
set -u
CKPT="$1"; OUT="$2"
rm -rf "$OUT"
/root/kiri_chain/infer_arm.sh "$CKPT" "$OUT" > "${OUT}.infer.log" 2>&1 &
PID=$!
for i in $(seq 1 300); do
  n=$(ls "$OUT/depth_est"/*.pfm 2>/dev/null | wc -l)
  [ "$n" -ge 132 ] && break
  kill -0 $PID 2>/dev/null || break
  sleep 4
done
sleep 5
kill $PID 2>/dev/null; wait $PID 2>/dev/null
echo "[1/3] 深度图 $(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l) 张"
cd /root/diffmvs
VAR_GATE=0 TEX_GATE=0 /root/kiri_chain/venv_mvs/bin/python -u /root/kiri_chain/fuse_only.py "$OUT" 3 "$OUT/pc_t3.ply" > "${OUT}.fuse.log" 2>&1
echo "[2/3] 融合完成: $(ls -la $OUT/pc_t3.ply 2>/dev/null | awk '{print $5}') 字节"
echo "[done]"
