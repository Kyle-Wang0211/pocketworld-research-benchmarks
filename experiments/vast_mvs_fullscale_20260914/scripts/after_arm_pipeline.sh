#!/bin/bash
# 训练结束 -> 自动出训后臂四件套(深度图 + thres2 ply + thres3 ply + bins)
# 用与训前臂【完全相同】的 /root/infer_arm.sh 和 /root/fuse_only.py,只换权重。
set -u
CK=/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt
echo "[wait] 等 $CK ..."
while [ ! -f "$CK" ]; do sleep 60; done
sleep 30   # 等 torch.save 落盘完成
echo "[wait] 到了: $(ls -la $CK)"
# 训练进程还在就再等(第二段跑完 epoch15 后才退出)
while pgrep -f "train.py.*casdiff_B_simpleproc" >/dev/null; do sleep 30; done
echo "[run] 推理(与训前臂同一脚本,只换 ckpt)"
/root/infer_arm.sh "$CK" /root/arm_after || exit 1
echo "[run] thres=3 融合"
cd /root/diffmvs && /venv/main/bin/python -u /root/fuse_only.py /root/arm_after 3 /root/arm_after/pc_t3.ply || exit 1
echo "[run] 转 bins"
/venv/main/bin/python /root/ply2bins.py /root/arm_after/pc.ply    /root/bins_B after_t2
/venv/main/bin/python /root/ply2bins.py /root/arm_after/pc_t3.ply /root/bins_B after_t3
echo "[done] 训后臂完成"
ls -la /root/bins_B
