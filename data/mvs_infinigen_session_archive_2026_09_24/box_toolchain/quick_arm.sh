#!/bin/bash
# 早期快照: 用 A+B 的中间 ckpt 出 thres=3 点云 + 多层判据。
# 与训前/训后① 走【完全同一条链】: infer_arm.sh -> fuse_only.py 3 -> plane_diag.py
# 唯一省略: infer_arm.sh 自带的 thres=2 融合(用不上),深度图满 132 张即终止该进程。
set -u
CKPT="$1"; OUT="$2"
rm -rf "$OUT"
/root/infer_arm.sh "$CKPT" "$OUT" > "${OUT}.infer.log" 2>&1 &
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
VAR_GATE=0 TEX_GATE=0 /venv/main/bin/python -u /root/fuse_only.py "$OUT" 3 "$OUT/pc_t3.ply" > "${OUT}.fuse.log" 2>&1
echo "[2/3] 融合完成: $(ls -la $OUT/pc_t3.ply 2>/dev/null | awk '{print $5}') 字节"
/venv/main/bin/python -u /root/plane_diag.py "$OUT/pc_t3.ply" > "${OUT}.diag.log" 2>&1
echo "[3/3] 多层判据:"
grep -E "检测到|平行面对数" "${OUT}.diag.log"
grep "面间距" "${OUT}.diag.log" | sort -t'【' -k2 -r | head -3
echo "[done]"
