#!/bin/bash
# 参照臂:两条分支的共同父节点 B15,以及 A+B 分支上用户肉眼判过的 ep0 / ep2。
# 没有这三个臂,「训练能不能压多层」就没有对照。
set -u
log(){ echo "[$(date +%H:%M:%S)] $*"; }
while [ ! -f /root/LG.DONE ]; do sleep 20; done
declare -a NAME=(B15par AB_ep0 AB_ep2)
declare -a CK=(/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt \
               /root/diffmvs/checkpoints/casdiff_AB/model_000000.ckpt \
               /root/diffmvs/checkpoints/casdiff_AB/model_000002.ckpt)
ARMS=""
for i in 0 1 2; do
  n=${NAME[$i]}; D=/root/lg_$n
  if [ "$(ls $D/depth_est 2>/dev/null | wc -l)" != "132" ]; then
    log "$n: 重跑推理"; /root/infer_arm.sh ${CK[$i]} $D > /root/lg_$n.infer.log 2>&1
    echo "  rc=$? depth=$(ls $D/depth_est 2>/dev/null | wc -l)"
  fi
  ARMS="$ARMS $n=$D"
done
for e in 0 1 2 3 4; do ARMS="$ARMS ep$e=/root/lg_ep$e"; done
log "八臂同口径总表"
/venv/main/bin/python /root/layer_gap_eps.py $ARMS
log "DONE"; touch /root/LG2.DONE
