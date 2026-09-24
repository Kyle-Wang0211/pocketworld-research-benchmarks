#!/bin/bash
# 自适应闸的第二个【官方】档: N0=1 (Temple 用的值), 保留室内的 A=4 / B=1300。
#   N0=2 (Museum 等 5 个室内场景): 最紧分支 = 0.5px 要 >=2 视图
#   N0=1 (Temple):                 多一条 0.25px 只要 >=1 视图 的分支 => 并集只会【增加】点
# 目的: 在不动算法、不出官方取值范围的前提下把覆盖找回来。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "融合 N0=1 档 (scan=Temple 取 [1,4,1500]) —— 🔴 注意 Temple 的 B=1500 不是 1300"
/venv/main/bin/python -u /root/fuse_dyn.py /root/lg_ep0 /root/dyn1_ep0.ply Temple 2>&1 | grep -vE "^processing|^valid" | tail -3
[ -f /root/dyn1_ep0.ply ] || { LOG "🔴 没出 ply"; exit 1; }
LOG "转 bins"
/venv/main/bin/python /root/ply2bins.py /root/dyn1_ep0.ply /root/bins_gm GM_dyn1 2>&1 | tail -1
LOG "尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 GM_t3 GM_dyn GM_dyn1 GM_rnd 2>&1 | grep -vE "less ref_view" | sed -n '/连通性/,/配对比较/p'
LOG "表面覆盖"
sed -i 's/TAGS = \["GM_t2", "GM_t3", "GM_dyn", "GM_rnd"\]/TAGS = ["GM_t2", "GM_t3", "GM_dyn", "GM_dyn1", "GM_rnd"]/' /root/cover_gm.py
sed -i 's/"GM_rnd": "随机抽稀(阴性对照)"}/"GM_rnd": "随机抽稀(阴性对照)", "GM_dyn1": "自适应 N0=1 (Temple档)"}/' /root/cover_gm.py
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -14
touch /root/DYN1_DONE
