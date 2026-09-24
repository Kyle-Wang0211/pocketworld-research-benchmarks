#!/bin/bash
# 仪器对照: 在同一批 ETH3D 点云上, 同时量【激光完整度】和【我那把覆盖率】。
# 若覆盖率在 ETH3D 上也是平的 ⇒ "+15.9pp vs +0.45pp" 是换尺子造成的假象, 结论作废。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
CKPT=/root/diffmvs_full/checkpoints/casdiff_full/model_000000.ckpt
run () { # scene tag max_h max_w px
  local out=/root/eth_out2/$1_$2
  [ -f $out/pc.ply ] && { LOG "  $1/$2 已有"; return; }
  mkdir -p $out; cd /root/diffmvs
  VAR_GATE=0 TEX_GATE=0 /venv/main/bin/python -u test.py \
    --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
    --testpath=/root/eth3d_mvs/$1 --testlist=/dev/null \
    --numdepth_initial=48 --numdepth=384 --max_h=$3 --max_w=$4 \
    --loadckpt="$CKPT" --outdir="$out" \
    --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --min_radius 0.125 --max_radius 8 \
    --photo_thres 0.3 0.5 0.5 --geo_mask_thres 1 --geo_pixel_thres $5 --geo_depth_thres 0.01 \
    > $out/run.log 2>&1
  LOG "  $1/$2 -> $(ls -la $out/pc.ply 2>/dev/null | awk '{printf "%.3f GB", $5/1e9}')"
}
LOG "重跑 office + delivery_area 两档"
run office        lo  512  768 0.8
run office        hi 1280 1920 2
run delivery_area lo  512  768 0.2
run delivery_area hi 1280 1920 0.5
touch /root/INSTR_DONE
