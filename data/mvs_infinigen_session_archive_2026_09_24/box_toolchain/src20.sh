#!/bin/bash
# 20 个源视图(官方口径)下重跑三档。10 src 的三档留在 bins_gm 里做对照。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p /root/pair20dir && cp /root/pair20u.txt /root/pair20dir/pair.txt
cd /root
for m in 2 3 dyn; do
  t=GM20_$m
  [ -f /root/bins_gm/$t.pos ] && { LOG "$t 已有, 跳过"; continue; }
  LOG "融合 $t  (20 src)"
  /venv/main/bin/python -u /root/fuse2.py /root/lg_ep0 /root/pair20dir /root/p20_$m.ply $m 2>&1 | grep -vE "^processing|^valid" | tail -2
  [ -f /root/p20_$m.ply ] || { LOG "🔴 $t 融合失败"; exit 1; }
  /venv/main/bin/python /root/ply2bins.py /root/p20_$m.ply /root/bins_gm $t 2>&1 | tail -1
done
LOG "尺子: 10src 三档 vs 20src 三档"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 GM_t3 GM_dyn GM20_2 GM20_3 GM20_dyn 2>&1 | grep -vE "less ref_view" | sed -n '/^臂/,$p'
LOG "表面覆盖"
/venv/main/bin/python - <<'PY'
import re, io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]', 'TAGS = ["GM_t2","GM_t3","GM_dyn","GM20_2","GM20_3","GM20_dyn"]', s)
s=re.sub(r'LAB = \{[^}]*\}',
 'LAB = {"GM_t2":"10src 固定2 (现役)","GM_t3":"10src 固定3","GM_dyn":"10src 自适应",'
 '"GM20_2":"20src 固定2","GM20_3":"20src 固定3","GM20_dyn":"20src 自适应 ★"}', s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -18
touch /root/SRC20_DONE
