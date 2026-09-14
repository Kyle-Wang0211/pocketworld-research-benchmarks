#!/bin/bash
# 多次采样方差:CasDiffMVS 是扩散模型, 官方配方 --ddim_eta 0 1 1 => 后两阶段随机采样。
# 白墙上代价曲线平 => 不同种子挑到不同深度;有纹理处曲线尖 => 各种子一致。
# 这是直接测"模型在不在瞎猜",与光度置信度正交。
#
# 🔴 噪声地板:cudnn.benchmark=True 会按计时选算法, 同种子两次也可能不同。
#    所以先跑 seed123 两遍当地板, 再跑不同种子。地板不减掉, 结论就不成立。
set -u
cd /root/diffmvs
RUN () {
  TAG=$1; SEED=$2
  OUT=/root/ms/$TAG
  [ -d "$OUT/depth_est" ] && [ "$(ls $OUT/depth_est | wc -l)" = "132" ] && { echo "SKIP $TAG"; return; }
  mkdir -p "$OUT"
  /venv/main/bin/python test.py --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
    --testpath=/root/mvs_P16k --outdir="$OUT" --loadckpt=/root/hs/ckpt_src/casdiffmvs_blendmvg.ckpt \
    --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
    --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --min_radius 0.125 --max_radius 8 --seed $SEED \
    --photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0 --geo_depth_thres 0.01 \
    > /root/ms/$TAG.log 2>&1
  n=$(head -c 250 "$OUT/pc.ply" 2>/dev/null | tr -d '\0' | grep -a "element vertex" | awk '{print $3}')
  echo "DONE $TAG seed=$SEED  pc=$n 点"
}
mkdir -p /root/ms
RUN floorA 123      # 噪声地板:同一种子
RUN floorB 123      # 噪声地板:同一种子, 第二遍
for s in 1 2 3 4 5 6; do RUN s$s $s; done
echo MULTISEED_DONE
