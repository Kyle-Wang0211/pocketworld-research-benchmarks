#!/usr/bin/env bash
# iter_015000.ckpt 一落盘,就用官方 test_dypcd_tnt_adv.py 在 132 张上跑两次:
#   A = 新 checkpoint     B = 起点 bld_best.ckpt(用户已判过"有白墙粘连")
# 两次参数逐字相同(官方 test_tnt_adv.sh 的旗,num_view 按我们 pair.txt 的 10+1),
# 这样差别只有权重一个变量。
set -u
CK=/root/MonoMVSNet/checkpoints/indoor_v3/iter_015000.ckpt
echo "[$(date +%H:%M:%S)] 等 $CK"
while [ ! -s "$CK" ]; do sleep 60; done
sleep 45
cd /root/MonoMVSNet
run () {   # $1=ckpt  $2=outdir 名
  echo "[$(date +%H:%M:%S)] 推理 $2"
  CUDA_VISIBLE_DEVICES=0 /venv/main/bin/python test_dypcd_tnt_adv.py \
    --dataset=tanks --batch_size=1 --testpath=/root/mono_data --testlist=lists/ours/test.txt \
    --loadckpt "$1" --outdir /root/MonoMVSNet/outputs/$2 \
    --ndepths 16,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --num_view=11 --num_worker 3 \
    --group_cor --attn_temp 2 --inverse_depth --max_h 832 --max_w 1152 \
    > /root/infer_$2.log 2>&1
  echo "  rc=$? 深度图=$(ls /root/MonoMVSNet/outputs/$2/scene0/depth_est 2>/dev/null | wc -l) ply=$(ls -l /root/MonoMVSNet/outputs/$2/*.ply 2>/dev/null | awk '{printf "%.0fMB", $5/1e6}')"
  tail -2 /root/infer_$2.log | cut -c1-130
}
run "$CK" v3_15k
run /root/MonoMVSNet/checkpoints/bld_ft/bld_best.ckpt base_same
echo "[$(date +%H:%M:%S)] DONE_WATCH"
