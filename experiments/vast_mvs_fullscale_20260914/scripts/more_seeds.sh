#!/bin/bash
# 加种子把方差估计的噪声压下去。std 估计量相对误差 ~ 1/sqrt(2(n-1)):
#   6 个种子 = 32%,16 个 = 18%。误删里属于"估计噪声"的那部分随之下降。
# 不改阈值、不加常数 —— 纯粹让同一把尺子更准。
set -u
cd /root/diffmvs
for s in 7 8 9 10 11 12 13 14 15 16; do
  OUT=/root/ms/s$s
  [ -d "$OUT/depth_est" ] && [ "$(ls $OUT/depth_est 2>/dev/null | wc -l)" = "132" ] && { echo "SKIP s$s"; continue; }
  mkdir -p "$OUT"
  /venv/main/bin/python test.py --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
    --testpath=/root/mvs_P16k --outdir="$OUT" --loadckpt=/root/hs/ckpt_src/casdiffmvs_blendmvg.ckpt \
    --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
    --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --min_radius 0.125 --max_radius 8 --seed $s \
    --photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0 --geo_depth_thres 0.01 \
    > /root/ms/s$s.log 2>&1
  echo "DONE s$s"
done
echo MORE_SEEDS_DONE
