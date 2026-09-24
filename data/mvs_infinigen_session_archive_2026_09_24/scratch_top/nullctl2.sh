#!/bin/bash
# 🔴 反方向阴性对照。
# 上次防的是「少留点 => 尺子机械性变好」(随机扔同样多点, 结果纹丝不动, 自适应的优势为真)。
# 这次新 ep0 【点更多】(41.38M vs 39.35M, +5.2%), 而 layerruler 的 MINPTS=4:
#   像素内点越多 => 越容易凑出第二簇 => 尺子会机械性地判它更差。
# 判据: 把新 ep0 【随机】抽稀到老 ep0 的点数。若读数掉回 ~62%, 则「新 ep0 更差」是密度假象。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
/venv/main/bin/python - <<'PY'
import numpy as np, os
pairs=[("NEW_t2","GM_t2","NEW_t2_dn"),("NEW20_dyn","GM20_dyn","NEW20_dyn_dn")]
for src,ref,out in pairs:
    if os.path.exists("/root/bins_gm/%s.pos"%out): print("  %s 已有"%out); continue
    n_t=os.path.getsize("/root/bins_gm/%s.pos"%ref)//12
    pos=np.fromfile("/root/bins_gm/%s.pos"%src,dtype="<f4").reshape(-1,3)
    col=np.fromfile("/root/bins_gm/%s.col"%src,dtype=np.uint8).reshape(-1,3)
    k=np.random.default_rng(0).permutation(pos.shape[0])[:n_t]; k.sort()
    pos[k].tofile("/root/bins_gm/%s.pos"%out); col[k].tofile("/root/bins_gm/%s.col"%out)
    print("  %-14s %s -> %s 点 (= %s 的点数)"%(out,format(pos.shape[0],","),format(n_t,","),ref))
PY
LOG "尺子: 加两个抽稀对照"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 NEW_t2 NEW_t2_dn GM20_dyn NEW20_dyn NEW20_dyn_dn 2>&1 \
  | grep -vE "less ref_view" | sed -n '/连通性/,/配对比较/p'
LOG "渲静图: 老 vs 新 (两组, 同机位)"
/venv/main/bin/python - > /root/mk2.py <<'PY'
print(open("/root/orbit_gm.py").read()
  .replace('A2 = Arm("GM_t2", "/root/bins_gm")','A2 = Arm(__import__("os").environ["L"], "/root/bins_gm")')
  .replace('A3 = Arm("GM_t3", "/root/bins_gm")','A3 = Arm(__import__("os").environ["R"], "/root/bins_gm")')
  .replace('OUT = "/root/gm_shots"','OUT = __import__("os").environ["O"]')
  .replace('("thres = 2    现役生产档", A2, "%s 点" % format(A2.n, ","))','(__import__("os").environ["LL"], A2, "%s 点" % format(A2.n, ","))')
  .replace('("thres = 3    候选 (更紧)", A3, "%s 点   -%.1f%%" % (format(A3.n, ","), 100.0*(A2.n-A3.n)/A2.n))','(__import__("os").environ["RL"], A3, "%s 点" % format(A3.n, ","))'))
PY
L=GM_t2     R=NEW_t2     LL="老 ep0   现役闸(10src 固2)" RL="★新 ep0 skyfix   同闸" O=/root/sh_gate /venv/main/bin/python -u /root/mk2.py 2>&1 | tail -5
L=GM20_dyn  R=NEW20_dyn  LL="老 ep0   20src 自适应"       RL="★新 ep0 skyfix   20src 自适应" O=/root/sh_dyn /venv/main/bin/python -u /root/mk2.py 2>&1 | tail -5
touch /root/NULL2_DONE
LOG DONE
