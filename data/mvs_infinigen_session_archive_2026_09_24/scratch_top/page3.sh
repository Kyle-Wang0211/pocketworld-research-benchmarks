#!/bin/bash
# 老 ep0 vs 新 ep0(skyfix), 同闸(现役 10src 固定2)。唯一变量 = 训练。
set -u
P=/root/page_ep0; rm -rf $P; mkdir -p $P/bin
for t in GM_t2 NEW_t2 NEW20_dyn; do for e in pos col; do
  ln -sf "$(readlink -f /root/bins_gm/$t.$e)" $P/bin/$t.$e; done; done
/venv/main/bin/python /root/gen_meta.py $P/bin GM_t2 NEW_t2 NEW20_dyn 2>&1 | tail -2
/venv/main/bin/python /root/build_page_cli.py --out $P --ref GM_t2 \
  --title "老 ep0 vs 新 ep0(skyfix)" \
  --h1 "老 ep0  vs  新 ep0(skyfix 重训)  —— 左中同闸(现役 10src 固定 thres=2), 唯一变量是训练; 右 = 新 ep0 配最好的闸" \
  --hint "新 ep0 的唯一训练变量 = TartanAir 天空深度范围修正(用官方天空标注重算 p1/p99)。左中两窗闸完全相同, 所以差别只来自权重。多层沿视线堆叠, 正视被 z-buffer 挡住 —— 请把仰角拖到接近水平看掠射面; 俯视角看覆盖有没有破洞。点大小调小一点分层更明显。" \
  --pane "老 ep0   现役闸::GM_t2::39,345,336 点 · 覆盖 91.93%" \
  --pane "新 ep0 skyfix   同一个闸::NEW_t2::41,377,512 点 · 覆盖 92.67%" \
  --pane "新 ep0 + 20src 自适应闸::NEW20_dyn::35,570,198 点 · 覆盖 89.18%"
pkill -f "http.server 8936" 2>/dev/null
cd $P && setsid nohup /venv/main/bin/python -m http.server 8936 --bind 127.0.0.1 > $P/http.log 2>&1 </dev/null &
sleep 2
ss -ltn 2>/dev/null | grep -q 8936 && echo "✅ 8936 在听 ($(du -sLh $P/bin | cut -f1))" || echo "🔴 8936 没起"
