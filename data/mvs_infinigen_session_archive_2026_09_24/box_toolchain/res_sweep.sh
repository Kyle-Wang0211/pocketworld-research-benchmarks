#!/bin/bash
# ep0 权重不动, 只换推理分辨率。融合口径与所有既有臂相同 (thres=3)。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
CK=/root/snap_ckpt/full_ep0.ckpt
for spec in 1504:2016:r2016 3008:4032:r4032; do
  MH=${spec%%:*}; rest=${spec#*:}; MW=${rest%%:*}; TAG=${rest##*:}
  D=/root/arm_ep0_$TAG
  if [ "$(ls $D/depth_est 2>/dev/null | wc -l)" != "132" ]; then
    LOG "$TAG 推理 ${MW}x${MH}"
    /root/infer_res.sh $CK $D $MH $MW > /root/$TAG.infer.log 2>&1
    LOG "  rc=$? depth=$(ls $D/depth_est 2>/dev/null | wc -l)  峰值显存见 nvidia-smi"
  fi
  if [ ! -f $D/pc_t3.ply ]; then
    LOG "$TAG 融合 thres=3"
    /venv/main/bin/python /root/fuse_only.py $D 3 $D/pc_t3.ply > /root/$TAG.fuse.log 2>&1
    LOG "  rc=$?  $(ls -la $D/pc_t3.ply 2>/dev/null | awk "{print \$5}") 字节"
  fi
done
LOG "全部完成"; touch /root/RES.DONE
