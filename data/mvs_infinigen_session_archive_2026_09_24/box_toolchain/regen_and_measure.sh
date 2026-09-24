#!/bin/bash
# Regenerate the depth maps the epoch snapshots threw away, then measure multilayer with the 09-13 instrument.
set -u
log(){ echo "[$(date +%H:%M:%S)] $*"; }
ARMS=""
for e in 0 1 2 3 4; do
  D=/root/lg_ep$e
  if [ ! -d $D/depth_est ] || [ "$(ls $D/depth_est 2>/dev/null | wc -l)" != "132" ]; then
    log "ep$e: 重跑推理(768x576,与快速臂同一条链)"
    /root/infer_arm.sh /root/snap_ckpt/full_ep$e.ckpt $D > /root/lg_ep$e.infer.log 2>&1
    echo "  rc=$? depth=$(ls $D/depth_est 2>/dev/null | wc -l)"
  else
    log "ep$e: 深度图已在"
  fi
  ARMS="$ARMS ep$e=$D"
done
log "量多层(layer_gap2 口径,逐像素全量,无随机)"
/venv/main/bin/python /root/layer_gap_eps.py $ARMS
log "DONE"; touch /root/LG.DONE
