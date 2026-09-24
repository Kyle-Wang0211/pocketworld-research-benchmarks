#!/bin/bash
# thres=2 vs thres=3 并排判决页。全量、零抽稀。
# 建页链逐字复用已建成的那套: gen_meta.py -> build_page_cli.py -> python -m http.server
# (两者都自带 _check_frames 预检: 字节数 == n*12, 且采样中位数与 meta 一致 => 防坐标系混用)
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/page_gm
rm -rf $P; mkdir -p $P/bin
cd /root

LOG "软链 bins (不复制, 省 1.1 GB 盘)"
for t in GM_t2 GM_t3; do
  for e in pos col; do
    ln -sf "$(readlink -f /root/bins_gm/$t.$e)" $P/bin/$t.$e
  done
done
ls -lL $P/bin/ | awk '{print "  "$9" "$5}'

LOG "生成 meta.json (含两项预检)"
/venv/main/bin/python /root/gen_meta.py $P/bin GM_t2 GM_t3 2>&1 | tail -4

LOG "建页"
/venv/main/bin/python /root/build_page_cli.py \
  --out $P --ref GM_t2 \
  --title "融合闸 thres=2 vs thres=3" \
  --h1 "融合几何闸 geo_mask_thres:  2 (现役) vs 3 (候选·更紧) — 全量 · 零抽稀 · 同一份 lg_ep0 深度图" \
  --hint "唯一变量 geo_mask_thres(要几个源视图同意才保留该点); geo_pixel_thres 两档恒 1.0。t3 已自证是 t2 的严格子集(100.0000%),收紧只做减法不移动点。尺子: 多层(片>=1000) 61.99% -> 56.96%,厚度中位 83.2mm -> 69.0mm,代价 -7.9% 点。多层沿视线堆叠,正视被遮挡,请压低仰角(拖动)看掠射面。" \
  --pane "thres = 2   现役生产档::GM_t2::39,345,336 点  |  多层 61.99%  |  厚度中位 83.2mm" \
  --pane "thres = 3   候选 · 更紧::GM_t3::36,233,955 点 (-7.9%)  |  多层 56.96%  |  厚度中位 69.0mm"

LOG "起服务"
pkill -f "http.server 8933" 2>/dev/null
cd $P && setsid nohup /venv/main/bin/python -m http.server 8933 --bind 127.0.0.1 > $P/http.log 2>&1 < /dev/null &
sleep 2
ss -ltn 2>/dev/null | grep 8933 && LOG "✅ 8933 在听" || LOG "🔴 8933 没起来"
LOG "页面总字节: $(du -sLh $P | cut -f1)"
