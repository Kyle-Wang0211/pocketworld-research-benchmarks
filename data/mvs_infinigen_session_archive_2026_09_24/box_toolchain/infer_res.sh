#!/bin/bash
# ============================================================================
# 分辨率可变版推理 —— 从 /root/infer_arm.sh 逐字复制, 唯一改动是 max_h/max_w 变成参数。
#
# 为什么这件事不需要重新训练:
#   官方 CasDiffMVS 训练吃 BlendedMVS 的 768×576, 推理时 test.py 默认 max_h=4800 max_w=6400,
#   三份官方测试脚本(eth3d/tank/dtu)【一个都不覆盖】=> ETH3D 高分档 6048×4032 原生全跑。
#   训练与推理差 8 倍线性是官方配方本身。级联代价体全卷积、深度范围来自 cam.txt。
#   我们的 infer_arm.sh 第 23 行自己标着 "--max_h 576 --max_w 768  我们的训练/推理分辨率"
#   —— 其余每一项都标了官方出处, 只有这一项是自定的。
#
#   内参会跟着缩: datasets/mvs.py::scale_img_adaptive 里
#     intrinsics[0,:] *= scale_w ; intrinsics[1,:] *= scale_h
#   并向下取整到 base=32 的倍数。我们的 cam.txt 内参本来就是按原生 4032×3024 写的
#   (cx=2021.7≈4032/2, cy=1513.2≈3024/2), 所以三档都自洽。
#
#   用法: infer_res.sh <ckpt> <out> <max_h> <max_w>
# ============================================================================
set -u
export VAR_GATE=0 TEX_GATE=0
CKPT="$1"; OUT="$2"; MH="$3"; MW="$4"
[ -f "$CKPT" ] || { echo "权重不存在: $CKPT"; exit 1; }
echo "[arm] VAR_GATE=$VAR_GATE TEX_GATE=$TEX_GATE (0=官方原逻辑)"
echo "[arm] ckpt=$CKPT  md5=$(md5sum "$CKPT" | cut -c1-14)  out=$OUT  max=${MW}x${MH}"
cd /root/diffmvs
exec /venv/main/bin/python -u test.py \
  --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=/root/mvs_P16k --testlist=/root/sp_testlist.txt \
  --numdepth_initial=48 --numdepth=384 --max_h=$MH --max_w=$MW \
  --loadckpt="$CKPT" --outdir="$OUT" \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 2 --geo_pixel_thres 1.0 --geo_depth_thres 0.01
