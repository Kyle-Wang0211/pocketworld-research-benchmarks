#!/bin/bash
# ep3(val 最低点) + ep7(第一小段终点) 两个快照,串行跑完再一起转 bins。
# 串行是为了不让两次推理抢 GPU、拖慢正在跑的训练。
set -u
LOG=/root/ep37_chain.log
exec >> "$LOG" 2>&1
echo "=== [$(date +%H:%M)] ep3+ep7 链条启动 ==="

echo "[1/4] 等 ep3 快照完成"
while ! grep -q "^\[done\]" /root/quick_ab_ep3.log 2>/dev/null; do
  grep -q "Traceback" /root/quick_ab_ep3.log 2>/dev/null && { echo "ep3 失败"; exit 1; }
  sleep 20
done
echo "[1/4] ep3 完成 $(date +%H:%M)"

echo "[2/4] 等 ep7 的 ckpt 落盘 + 训练进入 ep8"
CK=/root/diffmvs/checkpoints/casdiff_AB/model_000007.ckpt
while [ ! -f "$CK" ]; do sleep 30; done
sleep 20   # 等 torch.save 写完
cp "$CK" /root/ab_ep7.ckpt
echo "[2/4] ep7 ckpt 到位 md5=$(md5sum /root/ab_ep7.ckpt | cut -c1-14) $(date +%H:%M)"

echo "[3/4] 跑 ep7 快照"
/root/quick_arm.sh /root/ab_ep7.ckpt /root/arm_ab_ep7 || { echo "ep7 失败"; exit 1; }

echo "[4/4] 转 bins + 重算 meta"
/venv/main/bin/python /root/ply2bins.py /root/arm_ab_ep3/pc_t3.ply /root/bins_B ab_ep3 2>&1 | tail -2
/venv/main/bin/python /root/ply2bins.py /root/arm_ab_ep7/pc_t3.ply /root/bins_B ab_ep7 2>&1 | tail -2
/venv/main/bin/python /root/gen_meta.py /root/bins_B after_t3 ab_ep0 ab_ep2 ab_ep3 ab_ep5 ab_ep7 2>&1 | tail -4
echo "=== [$(date +%H:%M)] 链条完成,可以拉取 ==="
