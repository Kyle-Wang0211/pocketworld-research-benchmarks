#!/bin/bash
# ETH3D 阳性对照 —— 第 2 阶段
# 🔴 ETH3D 是 CC BY-NC-SA: 只做内部评测, 不进训练、不进出货。
#
# 权重 = 我们自己的 full_ep0 (不碰官方带 DTU 血统的权重)。
# 两档只差分辨率:
#   高档 1920x1280 = 官方 ETH3D 测试分辨率 (datasets/mvs.py:33)
#   低档  768x512  = 高档的 1/2.5
# geo_pixel_thres 按官方逐场景表 (test.py:264-290) 取高档值, 低档 = 高档/2.5 (物理等价):
#   office 2->0.8   delivery_area 0.5->0.2   pipes 2->0.8   kicker 1->0.4
# geo_mask_thres  = 1   (官方 test.py:237-263, 这四个场景全是 1)
# photo_thres     = 0.3 0.5 0.5 (官方 test_eth_casdiffmvs.sh:17)
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
CKPT=/root/diffmvs_full/checkpoints/casdiff_full/model_000000.ckpt

LOG "转换剩余场景"
for s in delivery_area pipes kicker; do
  if [ -d /root/eth3d_mvs/$s/cams ]; then
    LOG "  $s 已转 ($(ls /root/eth3d_mvs/$s/cams | wc -l) 视图)"
  else
    (cd /root/APD-MVS && /venv/main/bin/python /root/colmap2mvsnet_np2.py \
       --dense_folder /root/eth3d/$s --save_folder /root/eth3d_mvs/$s --model_ext .txt) >/dev/null 2>&1
    LOG "  $s: $(ls /root/eth3d_mvs/$s/cams 2>/dev/null | wc -l) 视图"
  fi
done

run_arm () {   # $1=scene $2=tag $3=max_h $4=max_w $5=geo_pixel_thres
  local s="$1" tag="$2" mh="$3" mw="$4" px="$5"
  local out=/root/eth_out/${s}_${tag}
  if [ -f "$out/pc.ply" ]; then LOG "  $s/$tag 已有"; return; fi
  mkdir -p "$out"
  cd /root/diffmvs
  VAR_GATE=0 TEX_GATE=0 /venv/main/bin/python -u test.py \
    --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
    --testpath=/root/eth3d_mvs/$s --testlist=/dev/null \
    --numdepth_initial=48 --numdepth=384 --max_h=$mh --max_w=$mw \
    --loadckpt="$CKPT" --outdir="$out" \
    --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --min_radius 0.125 --max_radius 8 \
    --photo_thres 0.3 0.5 0.5 --geo_mask_thres 1 --geo_pixel_thres $px --geo_depth_thres 0.01 \
    > "$out/run.log" 2>&1
  local sz
  sz=$(ls -la "$out/pc.ply" 2>/dev/null | awk '{printf "%.3f GB", $5/1e9}')
  LOG "  $s/$tag -> ${sz:-失败(见 $out/run.log)}"
}

# scene  低档px  高档px   —— 高档 = 官方逐场景值, 低档 = 高档/2.5
run_all () {
  run_arm office        lo  512  768 0.8 ; run_arm office        hi 1280 1920 2
  run_arm delivery_area lo  512  768 0.2 ; run_arm delivery_area hi 1280 1920 0.5
  run_arm pipes         lo  512  768 0.8 ; run_arm pipes         hi 1280 1920 2
  run_arm kicker        lo  512  768 0.4 ; run_arm kicker        hi 1280 1920 1
}
run_all

LOG "激光真值评测"
EV=/root/multi-view-evaluation/build/ETH3DMultiViewEvaluation
for s in office delivery_area pipes kicker; do
  for tag in lo hi; do
    P=/root/eth_out/${s}_${tag}/pc.ply
    [ -f "$P" ] || { echo "  $s/$tag : 无 ply"; continue; }
    "$EV" --reconstruction_ply_path "$P" \
          --ground_truth_mlp_path /root/eth3d/$s/dslr_scan_eval/scan_alignment.mlp \
          --tolerances 0.01,0.02,0.05,0.1 > /root/eth_out/${s}_${tag}/eval.txt 2>&1
    echo "  ${s}/${tag}"
    grep -iE "^(Tolerances|Completenesses|Accuracies|F1-scores)" /root/eth_out/${s}_${tag}/eval.txt | sed 's/^/     /'
  done
done
touch /root/ETHRUN_DONE
