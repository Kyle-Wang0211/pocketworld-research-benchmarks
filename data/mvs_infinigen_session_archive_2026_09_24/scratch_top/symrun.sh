#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
/venv/main/bin/python /root/symfuse.py || exit 1
# 用打了对称补丁的 filter 融合
cat > /root/fuse_sym.py <<'PY'
import os, sys, importlib.util
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
spec = importlib.util.spec_from_file_location("filter_sym", "/root/filter_sym.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT,PAIR,PLY,MT,PX,DT = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6])
print("[sym] mask>=%d px<%.4f depth<%.6f"%(MT,PX,DT), flush=True)
m.filter_depth(PAIR,OUT,PLY,MT,PX,DT,[0.3,0.5,0.5],"casdiffmvs","general")
PY
run(){ # tag script mask px depth
  [ -f /root/bins_gm/$1.pos ] && { LOG "$1 已有"; return; }
  LOG "融合 $1"
  /venv/main/bin/python -u /root/$2 /root/lg_ep0 /root/pair20dir /root/s_$1.ply $3 $4 $5 2>&1 | grep -vE "^processing|^valid" | tail -1
  [ -f /root/s_$1.ply ] && /venv/main/bin/python /root/ply2bins.py /root/s_$1.ply /root/bins_gm $1 2>&1 | tail -1
}
run PX0125 fuse3.py 2 0.125 0.01     # A: 官方 DTU 的像素闸
run SYM    fuse_sym.py 2 1.0   0.01  # B: 对称归一化, 其余与现役 20src 固定2 完全相同
LOG "尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 GM20_2 GM20_dyn PX0125 SYM 2>&1 | grep -vE "less ref_view" | sed -n '/连通性/,/配对比较/p'
LOG "表面覆盖"
/venv/main/bin/python - <<'PY'
import re,io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]','TAGS = ["GM_t2","GM20_2","GM20_dyn","PX0125","SYM"]',s)
s=re.sub(r'LAB = \{[^}]*\}','LAB = {"GM_t2":"现役 10src 固2","GM20_2":"20src 固2(基准)",'
 '"GM20_dyn":"20src 自适应","PX0125":"A 官方像素闸 0.125","SYM":"B 对称归一化 ★"}',s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -16
touch /root/SYM_DONE
LOG DONE
