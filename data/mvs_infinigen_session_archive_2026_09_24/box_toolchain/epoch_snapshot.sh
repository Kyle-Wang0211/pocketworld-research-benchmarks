#!/bin/bash
# 全量训练期间: 每出一个 model_XXXXXX.ckpt 就在同一块卡上出一版 thres=3 点云 + bins (与快档同一条链 quick_arm.sh)
# 用法: setsid nohup /root/epoch_snapshot.sh </dev/null >/dev/null 2>&1 &
LOG=/root/epoch_snapshot.log; exec >> $LOG 2>&1
CK=/root/diffmvs_full/checkpoints/casdiff_full; mkdir -p /root/bins_full /root/snap_ckpt
echo "=== [$(date +%m-%d\ %H:%M)] epoch_snapshot 起 ==="
while true; do
  for f in $(ls $CK/model_*.ckpt 2>/dev/null | sort); do
    n=$(basename $f .ckpt | sed "s/model_0*//"); n=${n:-0}; tag=full_ep$n
    [ -f /root/bins_full/$tag.pos ] && continue
    sleep 60   # 等 torch.save 写完
    cp $f /root/snap_ckpt/$tag.ckpt
    echo "[$(date +%H:%M)] $tag md5=$(md5sum /root/snap_ckpt/$tag.ckpt | cut -c1-12) 开始出点云"
    /root/quick_arm.sh /root/snap_ckpt/$tag.ckpt /root/arm_$tag > /root/quick_$tag.log 2>&1 || { echo "[$tag] quick_arm 失败"; continue; }
    /venv/main/bin/python /root/ply2bins.py /root/arm_$tag/pc_t3.ply /root/bins_full $tag 2>&1 | tail -1
    A=""; for p in /root/bins_full/*.pos; do A="$A $(basename $p .pos)"; done
    /venv/main/bin/python /root/gen_meta.py /root/bins_full $A 2>&1 | tail -1
    echo "[$(date +%H:%M)] $tag 完成: $(grep -o "[0-9,]* points" /root/quick_$tag.log | tail -1) -> /root/bins_full/$tag.{pos,col}"
    rm -rf /root/arm_$tag/depth_est /root/arm_$tag/confidence   # 深度图可再生, 只留 ply
    /venv/main/bin/python /root/epoch_eval.py full_v3 $n 2>&1 | grep -vE "less ref_view" | tee -a /root/epoch_eval.log
  done
  sleep 300
done
