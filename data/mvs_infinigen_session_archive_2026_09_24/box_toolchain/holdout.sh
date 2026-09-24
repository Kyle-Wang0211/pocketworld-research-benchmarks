#!/bin/bash
# 留出验证: 用户判过「768 thres=1 比 thres=3 多层和粘连都轻微增加」。
# 这组数据没有参与尺子的挑选, 是无偏检验。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
mkdir -p bins_ho
[ -f /root/ho_t3.ply ] || { LOG "融合 768 @ thres=3"; /venv/main/bin/python fuse_px.py /root/lg_ep0 3 /root/ho_t3.ply 1.0 2>&1 | tail -1; }
[ -f /root/ho_t1.ply ] || { LOG "融合 768 @ thres=1"; /venv/main/bin/python fuse_px.py /root/lg_ep0 1 /root/ho_t1.ply 1.0 2>&1 | tail -1; }
for p in ho_t3:HO_t3 ho_t1:HO_t1; do
  f=${p%%:*}; t=${p##*:}
  [ -f /root/bins_ho/$t.pos ] || /venv/main/bin/python ply2bins.py /root/$f.ply /root/bins_ho $t 2>&1 | tail -1
done
LOG "跑尺子"
/venv/main/bin/python -u layerruler.py --bins /root/bins_ho --tags HO_t3 HO_t1 2>&1 | sed -n "/连通性/,/配对比较/p"
touch /root/HO_DONE
