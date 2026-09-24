#!/bin/bash
# 用打了补丁的树重跑推理,存 expvar / secmass。
# 🔴 阴性对照: depth_est/*.pfm 必须与原版逐字节相同(补丁只增输出不改计算)。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
/venv/main/bin/python /root/fixtest.py || exit 1
export VAR_GATE=0 TEX_GATE=0
CKPT=/root/snap_ckpt/full_ep0.ckpt
OUT=/root/var_ep0
rm -rf $OUT
LOG "推理(打补丁的树),与 infer_arm.sh 逐字同参"
cd /root/diffmvs_var
/venv/main/bin/python -u test.py \
  --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=/root/mvs_P16k --testlist=/root/sp_testlist.txt \
  --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
  --loadckpt="$CKPT" --outdir="$OUT" \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 2 --geo_pixel_thres 1.0 --geo_depth_thres 0.01 \
  > /root/var_infer.log 2>&1
LOG "  rc=$? depth=$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l) expvar=$(ls $OUT/expvar/*.pfm 2>/dev/null | wc -l) secmass=$(ls $OUT/secmass/*.pfm 2>/dev/null | wc -l)"
[ "$(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l)" = "132" ] || { LOG "🔴 深度图不全"; tail -20 /root/var_infer.log; exit 1; }

LOG "🔴 阴性对照: 与原版 lg_ep0 的 depth_est 逐字节比"
SAME=0; DIFF=0
for f in $OUT/depth_est/*.pfm; do
  b=$(basename $f)
  if cmp -s "$f" "/root/lg_ep0/depth_est/$b"; then SAME=$((SAME+1)); else DIFF=$((DIFF+1)); fi
done
LOG "  逐字节相同 $SAME / 不同 $DIFF  $([ $DIFF -eq 0 ] && echo '✅ 补丁未改变任何计算' || echo '🔴 补丁改了计算, 结论不可用')"
touch /root/VAR_DONE
