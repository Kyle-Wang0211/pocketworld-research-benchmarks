#!/bin/bash
# 诊断结论: 自适应的 9 条分支里, i=2 之外的 8 条【边际贡献合计仅 ~1.2%】
# => 在我们的场景上, 自适应 ≈ 单一固定闸 (0.50px, 相对深度 0.00154, >=2 视图)
# 直接验证这个等价性, 并拆开两个容差各自的贡献。全部用 filter_depth 固定闸, 20 src。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
# 给 fuse2.py 加一个"自定两容差"的模式
cat > /root/fuse3.py <<'PY'
import os, sys
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth
OUT,PAIR,PLY,MT,PX,DT = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6])
print("[f3] mask>=%d  pixel<%.4f  depth<%.6f" % (MT,PX,DT), flush=True)
filter_depth(PAIR,OUT,PLY,MT,PX,DT,[0.3,0.5,0.5],"casdiffmvs","general")
PY
run(){ # tag mask px depth
  [ -f /root/bins_gm/$1.pos ] && { LOG "$1 已有"; return; }
  LOG "融合 $1  (mask>=$2  px<$3  depth<$4)"
  /venv/main/bin/python -u /root/fuse3.py /root/lg_ep0 /root/pair20dir /root/f3_$1.ply $2 $3 $4 2>&1 | grep -vE "^processing|^valid" | tail -1
  /venv/main/bin/python /root/ply2bins.py /root/f3_$1.ply /root/bins_gm $1 2>&1 | tail -1
}
# A: 完全等价于自适应的 i=2 分支
run EQ_i2    2 0.5 0.00154
# B: 只把【深度容差】收紧到 i=2 那档, 像素容差保持我们的 1.0
run EQ_depth 2 1.0 0.00154
# C: 只把【像素容差】收紧, 深度保持我们的 0.01
run EQ_px    2 0.5 0.01
LOG "尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 GM20_2 GM20_dyn EQ_i2 EQ_depth EQ_px 2>&1 | grep -vE "less ref_view" | sed -n '/^臂/,/配对比较/p'
LOG "覆盖"
/venv/main/bin/python - <<'PY'
import re,io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]','TAGS = ["GM_t2","GM20_2","GM20_dyn","EQ_i2","EQ_depth","EQ_px"]',s)
s=re.sub(r'LAB = \{[^}]*\}','LAB = {"GM_t2":"现役 10src 固2","GM20_2":"20src 固2","GM20_dyn":"20src 自适应",'
 '"EQ_i2":"固定=i2分支 .5px/.00154","EQ_depth":"只紧深度 1px/.00154","EQ_px":"只紧像素 .5px/.01"}',s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -18
touch /root/BR2_DONE
