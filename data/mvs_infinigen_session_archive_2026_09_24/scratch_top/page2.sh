#!/bin/bash
# 两窗判决页: 现役(10src 固定2) vs 修了 pair.txt 缺陷后的官方自适应(20src)
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/page_final; rm -rf $P; mkdir -p $P/bin
for t in GM_t2 GM20_dyn; do for e in pos col; do
  ln -sf "$(readlink -f /root/bins_gm/$t.$e)" $P/bin/$t.$e; done; done
/venv/main/bin/python /root/gen_meta.py $P/bin GM_t2 GM20_dyn 2>&1 | tail -3
/venv/main/bin/python /root/build_page_cli.py --out $P --ref GM_t2 \
  --title "现役 vs 官方自适应(修完 pair 缺陷)" \
  --h1 "老 ep0 · 同一份深度图 · 左=现役生产档 / 右=官方自适应几何闸 D2HC(已修 pair.txt 只给 10 个源视图的缺陷)" \
  --hint "🔴修掉的缺陷: filter.py 融合遍历 pair.txt 全部 src 不截断(:166/:382), 只有推理截断(mvs.py:134); 官方转换器写死 num_view=min(20,N-1)(colmap2mvsnet_np2.py:418), 官方 ETH3D 实测每 ref 20 个, 我们那份 8 月的只有 10 个 => 自适应闸的绝对阈值(>=10 视图)对我们等于全票、对官方只是半数。右窗已补到 20(旧 10 个逐字不动+官方评分补 10)。 数: 多层(片>=1000) 61.99% -> 48.75%, 厚度中位 83.2 -> 50.4mm, 表面覆盖 91.93% -> 88.39%(现役覆盖的像素里仍保 95.94%)。多层沿视线堆叠, 正视被 z-buffer 挡住, 请压低仰角看掠射面; 俯视角看有没有多出空洞。" \
  --pane "现役  10src · 固定 thres=2::GM_t2::39,345,336 点 | 多层 61.99% | 厚度 83.2mm | 覆盖 91.93%" \
  --pane "官方自适应  20src · D2HC::GM20_dyn::34,071,655 点 | 多层 48.75% | 厚度 50.4mm | 覆盖 88.39%"
pkill -f "http.server 8935" 2>/dev/null
cd $P && setsid nohup /venv/main/bin/python -m http.server 8935 --bind 127.0.0.1 > $P/http.log 2>&1 </dev/null &
sleep 2
ss -ltn 2>/dev/null | grep -q 8935 && LOG "✅ 8935 在听  ($(du -sLh $P/bin | cut -f1))" || LOG "🔴 8935 没起"
