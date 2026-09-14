#!/usr/bin/env bash
# epoch 0 的 finalmodel_0.ckpt 一落盘且写完,就自动跑推理+融合+转 bins。
# 推理参数与 mono_20260910 页面的②逐字相同(test_dtu_pcd.py + TNT/Museum 融合),
# 唯一变量 = 权重 ⇒ 可与 bld_best / v3-finalmodel_0 三方并排。
# 🔴 规矩:不许静默出口,每一步失败都要留痕并写进 STATUS。
set -u
CK=/root/MonoMVSNet/checkpoints/indoor_v4/finalmodel_0.ckpt
SNAP=/root/ckpt_park/v4_ep0.ckpt
OUT=/root/MonoMVSNet/outputs/v4ep0
PAIRD=/root/mono_dypcd_v4ep0/scene0   # 🔴 basename 必须是 scene0:filter_depth 拿它当 scan 键查常数表
PLY=/root/regionmerge/mono_v4ep0.ply
STATUS=/root/watch_ep0.status
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a $STATUS; }

say "WAITING for $CK"
prev=-1
while true; do
  if [ -f "$CK" ]; then
    cur=$(stat -c %s "$CK" 2>/dev/null || echo 0)
    [ "$cur" = "$prev" ] && [ "$cur" -gt 100000000 ] && break     # 连续两次同尺寸且>100MB = 写完
    prev=$cur
  fi
  sleep 30
done
mkdir -p /root/ckpt_park && cp "$CK" "$SNAP"
say "CKPT ready $(stat -c %s $SNAP) bytes -> 快照 $SNAP"

say "STEP1 推理 (test_dtu_pcd.py, 与②同参, 权重=v4 epoch0)"
cd /root/MonoMVSNet
/venv/main/bin/python test_dtu_pcd.py --dataset=general_eval_vit --batch_size=1 \
  --testpath=/root/mono_data --testlist=lists/ours/test.txt \
  --loadckpt "$SNAP" --outdir "$OUT" \
  --thres_view 2 --ndepths 8,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --conf 0.6 \
  --group_cor --attn_temp 2 --inverse_depth --num_view 21 --num_worker 2 \
  > /root/v4ep0_infer.log 2>&1
rc=$?
n=$(ls "$OUT"/scene0/depth_est 2>/dev/null | wc -l)
say "STEP1 rc=$rc 深度产物=$n 个 (脚本自带融合会因场景名 scene0 崩,属已知,不影响深度)"
if [ "$n" -lt 132 ]; then say "🔴 ABORT: 深度图不足 132,看 /root/v4ep0_infer.log"; exit 1; fi

say "STEP2 官方 TNT/Museum 融合"
rm -rf "$PAIRD"
SRC="$OUT/scene0" PAIRDIR="$PAIRD" OUTPLY="$PLY" \
  /venv/main/bin/python /root/mono_dypcd.py > /root/v4ep0_fuse.log 2>&1
rc=$?
sz=$(stat -c %s "$PLY" 2>/dev/null || echo 0)
say "STEP2 rc=$rc ply=$((sz/1000000)) MB"
if [ "$sz" -lt 10000000 ]; then say "🔴 ABORT: ply 太小或缺失,看 /root/v4ep0_fuse.log"; exit 1; fi

say "STEP3 转 bins"
/root/da3venv/bin/python /root/ply2bins.py "$PLY" /root/bins_mono monov4ep0 >> /root/v4ep0_fuse.log 2>&1
rc=$?
p=$(stat -c %s /root/bins_mono/monov4ep0.pos 2>/dev/null || echo 0)
c=$(stat -c %s /root/bins_mono/monov4ep0.col 2>/dev/null || echo 0)
say "STEP3 rc=$rc pos=$p 字节 ($((p/12)) 点) col=$c 字节"
if [ "$p" -lt 1000000 ]; then say "🔴 ABORT: bins 异常"; exit 1; fi

say "DONE_V4EP0  点数=$((p/12))  待下载: /root/bins_mono/monov4ep0.{pos,col}"
