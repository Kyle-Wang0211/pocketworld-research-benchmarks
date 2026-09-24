#!/bin/bash
# geo_mask_thres 3 / 2 / 1 完整梯子 —— 三朵云【全部已存在】, 不做任何新融合。
#   thres=3  /root/bins_ho/HO_t3   (holdout.sh 02:40 融合, 源 = /root/lg_ep0 深度图)
#   thres=2  /root/lg_ep0/pc.ply   (infer_arm.sh 原生产出, 同一份深度图)
#   thres=1  /root/bins_ho/HO_t1   (holdout.sh 02:40 融合, 同一份深度图)
# 唯一变量 = geo_mask_thres。geo_pixel_thres 三档全是 1.0。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p /root/bins_gm
cd /root

# thres=2 转 bins (唯一缺的一个)
if [ ! -f /root/bins_gm/GM_t2.pos ]; then
  LOG "thres=2 -> bins (ply2bins, 含帧自证)"
  /venv/main/bin/python ply2bins.py /root/lg_ep0/pc.ply /root/bins_gm GM_t2 2>&1 | tail -3
fi
# 另两档软链进来, 好让尺子一次出三行
for s in t3 t1; do
  for e in pos col; do
    [ -e /root/bins_gm/GM_$s.$e ] || ln -s /root/bins_ho/HO_$s.$e /root/bins_gm/GM_$s.$e
  done
done

LOG "点数(覆盖) —— 尺子【不含】覆盖项, 必须单独看"
/venv/main/bin/python - <<'PY'
import os
for t,lab in (("GM_t3","thres=3"),("GM_t2","thres=2"),("GM_t1","thres=1")):
    n=os.path.getsize("/root/bins_gm/%s.pos"%t)//12
    print("  %-8s %-10s %14s 点" % (t,lab,format(n,",")))
PY

LOG "跑尺子 (同一口径, 同 16 个相机)"
/venv/main/bin/python -u layerruler.py --bins /root/bins_gm --tags GM_t3 GM_t2 GM_t1 2>&1 | grep -vE "less ref_view"
LOG DONE
touch /root/GM_DONE
