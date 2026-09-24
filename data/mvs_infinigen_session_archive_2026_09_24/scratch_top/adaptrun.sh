#!/bin/bash
# 充分条件测试: 逐像素放宽 geo_depth_thres 能不能跳出「压多层=付覆盖」的前沿。
# 全部在 /root/var_ep0(打补丁那次推理的深度图)上跑, 基线也用它 => 同源可比。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
cat > /root/fuse_adapt.py <<'PY'
import os, sys, importlib.util
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
spec = importlib.util.spec_from_file_location("fa","/root/filter_adapt.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT,PAIR,PLY,MT,PX,DT = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6])
print("[adapt] mask>=%d px<%.4f depth<%.6f (dthres/ 存在则逐像素)"%(MT,PX,DT), flush=True)
m.filter_depth(PAIR,OUT,PLY,MT,PX,DT,[0.3,0.5,0.5],"casdiffmvs","general")
PY

# ---- 基线: 同一份深度图 + 固定阈值(无 dthres 目录) ----
rm -rf /root/var_ep0/dthres
if [ ! -f /root/bins_gm/VB_base.pos ]; then
  LOG "基线 VB_base (固定 0.01, 同源)"
  /venv/main/bin/python -u /root/fuse_adapt.py /root/var_ep0 /root/pair20dir /root/vb_base.ply 2 1.0 0.01 2>&1 | grep -vE "^processing|^valid" | tail -1
  /venv/main/bin/python /root/ply2bins.py /root/vb_base.ply /root/bins_gm VB_base 2>&1 | tail -1
fi
# 🔴 阳性对照: dthres 全填 0.01 => 必须与基线【点数完全相同】, 否则逐像素通路本身有 bug
if [ ! -f /root/bins_gm/VB_ident.pos ]; then
  LOG "🔴 阳性对照 VB_ident (dthres 全填 0.01, 应与基线点数完全相同)"
  /venv/main/bin/python /root/mkdthres.py /root/var_ep0 0.0 0.01 2>&1 | tail -2
  /venv/main/bin/python -u /root/fuse_adapt.py /root/var_ep0 /root/pair20dir /root/vb_ident.ply 2 1.0 0.01 2>&1 | grep -vE "^processing|^valid" | tail -1
  /venv/main/bin/python /root/ply2bins.py /root/vb_ident.ply /root/bins_gm VB_ident 2>&1 | tail -1
fi
# ---- 扫 k ----
for K in 4 12 40; do
  T=VB_k$K
  [ -f /root/bins_gm/$T.pos ] && { LOG "$T 已有"; continue; }
  LOG "扫 k=$K"
  /venv/main/bin/python /root/mkdthres.py /root/var_ep0 $K 0.01 2>&1 | tail -1
  /venv/main/bin/python -u /root/fuse_adapt.py /root/var_ep0 /root/pair20dir /root/vb_k$K.ply 2 1.0 0.01 2>&1 | grep -vE "^processing|^valid" | tail -1
  /venv/main/bin/python /root/ply2bins.py /root/vb_k$K.ply /root/bins_gm $T 2>&1 | tail -1
done
rm -rf /root/var_ep0/dthres
LOG "尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags VB_base VB_ident VB_k4 VB_k12 VB_k40 GM20_dyn 2>&1 | grep -vE "less ref_view" | sed -n '/连通性/,/配对比较/p'
LOG "覆盖"
/venv/main/bin/python - <<'PY'
import re,io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]','TAGS = ["VB_base","VB_ident","VB_k4","VB_k12","VB_k40","GM20_dyn"]',s)
s=re.sub(r'LAB = \{[^}]*\}','LAB = {"VB_base":"基线 固定0.01","VB_ident":"阳性对照 逐像素全0.01",'
 '"VB_k4":"逐像素 k=4","VB_k12":"逐像素 k=12","VB_k40":"逐像素 k=40","GM20_dyn":"官方自适应(参照)"}',s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -18
touch /root/ADAPT_DONE
LOG DONE
