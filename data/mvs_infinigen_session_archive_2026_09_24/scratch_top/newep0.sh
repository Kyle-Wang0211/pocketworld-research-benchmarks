#!/bin/bash
# 新 ep0 (skyfix) 全套对照。唯一训练变量 = TartanAir 天空深度范围修正。
# 比较必须【同闸】, 否则又是两个变量:
#   ① 新 vs 老, 都用现役闸 (10src, 固定 thres=2)      <- 回答「训练改动有没有用」
#   ② 新 vs 老, 都用最佳闸 (20src, 官方自适应 D2HC)    <- 回答「最新最强是什么样」
#   ③ 新 ep0 自己的闸梯子                              <- 确认闸的结论在新权重上也成立
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
CK=/root/diffmvs_full/checkpoints/casdiff_full_skyfix/model_000000.ckpt
OUT=/root/sky_ep0
cp -n $CK /root/snap_ckpt/sky_ep0.ckpt 2>/dev/null
LOG "权重 md5=$(md5sum $CK | cut -c1-14)  (老 ep0 是 e71dc850478eaf)"

# ---------- A 推理 (与老 ep0 逐字同口径: infer_arm.sh, 768x576) ----------
if [ "$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l)" != "132" ]; then
  LOG "推理新 ep0 (768x576, 同 infer_arm.sh)"
  /root/infer_arm.sh $CK $OUT > /root/sky_ep0.infer.log 2>&1
  LOG "  rc=$? 深度图 $(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l) 张"
fi
[ "$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l)" = "132" ] || { LOG "🔴 深度图不全, 停"; exit 1; }

# infer_arm.sh 自带的收尾融合就是 10src+thres=2 = 现役闸
if [ -f $OUT/pc.ply ] && [ ! -f /root/bins_gm/NEW_t2.pos ]; then
  LOG "转 bins: NEW_t2 (10src 固定2 = 现役闸)"
  /venv/main/bin/python /root/ply2bins.py $OUT/pc.ply /root/bins_gm NEW_t2 2>&1 | tail -1
fi

# ---------- B 20src 两档 ----------
fuse(){ # tag mode
  [ -f /root/bins_gm/$1.pos ] && { LOG "$1 已有"; return; }
  LOG "融合 $1 (20src, mode=$2)"
  /venv/main/bin/python -u /root/fuse2.py $OUT /root/pair20dir /root/n20_$2.ply $2 2>&1 | grep -vE "^processing|^valid" | tail -1
  /venv/main/bin/python /root/ply2bins.py /root/n20_$2.ply /root/bins_gm $1 2>&1 | tail -1
}
fuse NEW20_2   2
fuse NEW20_dyn dyn

# ---------- C 尺子 + 覆盖 ----------
LOG "尺子: 老三档 vs 新三档 (同口径 16 机位)"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm \
  --tags GM_t2 NEW_t2 GM20_2 NEW20_2 GM20_dyn NEW20_dyn 2>&1 | grep -vE "less ref_view" | sed -n '/^臂/,$p'
LOG "表面覆盖"
/venv/main/bin/python - <<'PY'
import re,io
p="/root/cover_gm.py"; s=io.open(p,encoding="utf-8").read()
s=re.sub(r'TAGS = \[[^\]]*\]','TAGS = ["GM_t2","NEW_t2","GM20_2","NEW20_2","GM20_dyn","NEW20_dyn"]',s)
s=re.sub(r'LAB = \{[^}]*\}','LAB = {"GM_t2":"老ep0 10src 固2(现役)","NEW_t2":"★新ep0 10src 固2",'
 '"GM20_2":"老ep0 20src 固2","NEW20_2":"★新ep0 20src 固2",'
 '"GM20_dyn":"老ep0 20src 自适应","NEW20_dyn":"★新ep0 20src 自适应"}',s)
io.open(p,"w",encoding="utf-8").write(s)
PY
/venv/main/bin/python -u /root/cover_gm.py 2>&1 | tail -18
touch /root/NEWEP0_DONE
LOG "DONE"
