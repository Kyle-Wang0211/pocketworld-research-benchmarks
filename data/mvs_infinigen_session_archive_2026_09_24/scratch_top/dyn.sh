#!/bin/bash
# 老 ep0 同一份深度图, 三档几何闸对照: 固定2 / 固定3 / 官方自适应(D2HC)
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "融合: 官方自适应几何一致性 (D2HC, 室内三元组 [2,4,1300])"
/venv/main/bin/python -u /root/fuse_dyn.py /root/lg_ep0 /root/dyn_ep0.ply Museum 2>&1 | grep -vE "^processing" | tail -5
[ -f /root/dyn_ep0.ply ] || { LOG "🔴 没出 ply"; exit 1; }
LOG "  ply $(stat -c%s /root/dyn_ep0.ply) 字节"

LOG "转 bins"
/venv/main/bin/python /root/ply2bins.py /root/dyn_ep0.ply /root/bins_gm GM_dyn 2>&1 | tail -2

LOG "三档同口径量尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm --tags GM_t3 GM_t2 GM_dyn 2>&1 | grep -vE "less ref_view"

LOG "建三窗页 (新目录/新端口, 不动你正在看的 8933)"
P=/root/page_dyn; rm -rf $P; mkdir -p $P/bin
for t in GM_t2 GM_t3 GM_dyn; do for e in pos col; do
  ln -sf "$(readlink -f /root/bins_gm/$t.$e)" $P/bin/$t.$e; done; done
/venv/main/bin/python /root/gen_meta.py $P/bin GM_t2 GM_t3 GM_dyn 2>&1 | tail -2
/venv/main/bin/python /root/build_page_cli.py --out $P --ref GM_t2 \
  --title "几何闸三档: 固定2 / 固定3 / 官方自适应" \
  --h1 "老 ep0 · 同一份深度图 · 三档几何一致性闸: 固定 thres=2 / 固定 thres=3 / 官方自适应 D2HC" \
  --hint "光度闸三档完全相同(casdiffmvs 分支逐字相同, photo_thres 恒 [0.3,0.5,0.5]); 唯一变量=几何闸。自适应档=上游 filter_depth_dynamic(D2HC-RMVSNet, ECCV2020), 官方室内三元组 [N0=2,A=4,B=1300]: 容差越松要求同意的视图越多(0.5px 只要 2 视图 / 2.5px 要 10 视图), 落在曲线任一点即保留。多层沿视线堆叠,请压低仰角看掠射面。" \
  --pane "固定 thres = 2   现役::GM_t2::PLACEHOLDER2" \
  --pane "固定 thres = 3::GM_t3::PLACEHOLDER3" \
  --pane "官方自适应 D2HC::GM_dyn::PLACEHOLDERD"
pkill -f "http.server 8934" 2>/dev/null
cd $P && setsid nohup /venv/main/bin/python -m http.server 8934 --bind 127.0.0.1 > $P/http.log 2>&1 < /dev/null &
sleep 2
ss -ltn 2>/dev/null | grep -q 8934 && LOG "✅ 8934 在听" || LOG "🔴 8934 没起"
touch /root/DYN_DONE
