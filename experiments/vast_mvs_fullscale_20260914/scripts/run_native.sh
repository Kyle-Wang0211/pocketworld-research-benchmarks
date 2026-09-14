#!/bin/bash
# 官方分辨率推理:不传 --max_h/--max_w, 与官方 scripts/test/test_eth_casdiffmvs.sh 完全一致,
# 用 test.py 的默认 4800x6400。我们的输入 4032x3024 小于上限 => 原生分辨率, 零缩放。
# 其余参数与 casdiffmvs_run_official.sh 逐字相同。
set -u
cd /root/diffmvs
OUT=/root/off_native
mkdir -p "$OUT"
nvidia-smi --query-gpu=memory.total --format=csv,noheader
/venv/main/bin/python test.py --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=/root/mvs_P16k --outdir="$OUT" --loadckpt=/root/hs/ckpt_src/casdiffmvs_blendmvg.ckpt \
  --numdepth_initial=48 --numdepth=384 \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0 --geo_depth_thres 0.01
rc=$?
n=$(head -c 250 "$OUT/pc.ply" 2>/dev/null | tr -d '\0' | grep -a "element vertex" | awk '{print $3}')
echo "DONE_NATIVE rc=$rc pc=$n 点  (768 官方 = 36,845,259)"
