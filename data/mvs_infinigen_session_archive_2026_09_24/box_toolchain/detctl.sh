#!/bin/bash
# 分清两件事:
#   (a) 我的补丁改了计算
#   (b) 推理本身就有非确定性(09-22 已有旁证: 重融合差 1,162 点)
# 判据: 用【未打补丁的原版树】再跑一次, 与 lg_ep0 比。
#   若原版 vs 原版 也逐字节不同 => 是 (b), 补丁清白;
#   再比「补丁 vs 原版」的差异幅度是否与「原版 vs 原版」同量级。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
export VAR_GATE=0 TEX_GATE=0
OUT=/root/det_ep0
if [ "$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l)" != "132" ]; then
  rm -rf $OUT
  LOG "原版树再跑一次(同参同权重)"
  /root/infer_arm.sh /root/snap_ckpt/full_ep0.ckpt $OUT > /root/det_infer.log 2>&1
  LOG "  rc=$? depth=$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l)"
fi
LOG "三方比较"
/venv/main/bin/python -u - <<'PY'
import glob, os, sys, numpy as np
sys.path.insert(0,"/root/diffmvs")
from filter import read_pfm
def cmpdir(a, b, lab):
    same=0; diffs=[]; rel=[]
    fs = sorted(glob.glob(os.path.join(a,"depth_est","*.pfm")))
    for f in fs:
        g = os.path.join(b,"depth_est",os.path.basename(f))
        if not os.path.exists(g): continue
        if open(f,'rb').read() == open(g,'rb').read(): same+=1; continue
        x=read_pfm(f)[0]; y=read_pfm(g)[0]
        m=(x>0)&(y>0)
        if m.sum():
            d=np.abs(x[m]-y[m]); diffs.append(d.max()); rel.append(np.median(d/np.maximum(x[m],1e-6)))
    print("  %-34s 逐字节同 %3d/%d | 最大绝对差(各图max的中位) %.3e m | 相对差中位 %.3e"
          % (lab, same, len(fs), np.median(diffs) if diffs else 0, np.median(rel) if rel else 0), flush=True)
cmpdir("/root/det_ep0","/root/lg_ep0","原版 vs 原版 (非确定性地板)")
cmpdir("/root/var_ep0","/root/lg_ep0","补丁 vs 原版")
cmpdir("/root/var_ep0","/root/det_ep0","补丁 vs 原版第二跑")
PY
touch /root/DET_DONE
