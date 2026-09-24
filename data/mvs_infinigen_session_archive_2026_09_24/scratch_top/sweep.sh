#!/bin/bash
# 官方自适应闸的【全部】参数组合 —— 不外推, 只跑 filter.py:308-324 三张表里真实存在的三元组。
# 14 个 Tanks 场景去重后只有 8 组:
#   [2,12,1600] Family      [9,8,1600] Francis     [2,4,1300] Horse/室内五场景(已跑)
#   [6,8,1600] Lighthouse   [4,8,1600] M60         [3,4,1300] Panther
#   [3,4,1600] Train        [1,4,1500] Temple(已跑)
# 全部在老 ep0 + 20src 上跑, 与 GM20_dyn(=[2,4,1300]) 严格同口径。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
declare -A T=( [Family]="2,12,1600" [Francis]="9,8,1600" [Lighthouse]="6,8,1600" \
               [M60]="4,8,1600" [Panther]="3,4,1300" [Train]="3,4,1600" )
for s in Family Francis Lighthouse M60 Panther Train; do
  tag=DY_$s
  [ -f /root/bins_gm/$tag.pos ] && { LOG "$tag 已有"; continue; }
  LOG "融合 $tag  三元组 [${T[$s]}]"
  /venv/main/bin/python -u /root/fuse_dyn.py /root/lg_ep0 /root/dy_$s.ply $s 2>&1 | grep -vE "^processing|^valid" | tail -1
  [ -f /root/dy_$s.ply ] || { LOG "  🔴 $tag 失败"; continue; }
  /venv/main/bin/python /root/ply2bins.py /root/dy_$s.ply /root/bins_gm $tag 2>&1 | tail -1
done
LOG "尺子: 八组官方三元组 + 两个固定闸基准"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 GM20_2 GM20_dyn DY_Panther DY_Train DY_M60 DY_Lighthouse DY_Family DY_Francis \
  2>&1 | grep -vE "less ref_view" | sed -n '/连通性/,/配对比较/p'
LOG "表面覆盖"
/venv/main/bin/python - <<'PY'
import re,io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]','TAGS = ["GM_t2","GM20_2","GM20_dyn","DY_Panther","DY_Train","DY_M60","DY_Lighthouse","DY_Family","DY_Francis"]',s)
s=re.sub(r'LAB = \{[^}]*\}','LAB = {"GM_t2":"现役 10src 固2","GM20_2":"20src 固2",'
 '"GM20_dyn":"自适应[2,4,1300] 室内","DY_Panther":"自适应[3,4,1300]","DY_Train":"自适应[3,4,1600]",'
 '"DY_M60":"自适应[4,8,1600]","DY_Lighthouse":"自适应[6,8,1600]","DY_Family":"自适应[2,12,1600]",'
 '"DY_Francis":"自适应[9,8,1600]"}',s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -22
touch /root/SWEEP_DONE
LOG DONE
