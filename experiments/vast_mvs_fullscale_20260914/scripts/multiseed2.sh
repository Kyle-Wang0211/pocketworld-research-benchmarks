#!/bin/bash
# 训前/训后 权重的多种子方差测量。
# 与 09-09 /root/multiseed.sh 同法,但:
#   (a) 口径改为 infer_arm.sh 的 ETH3D 档(geo_mask_thres=2),两臂一致
#   (b) 只要 depth_est(方差只需深度图),满 132 张即停,省掉每轮 20 分钟融合
#   (c) 两个权重都跑,严格单变量
# 🔴 噪声地板必须先跑: cudnn.benchmark=True 按计时选算法,同种子两次也可能不同。
#    地板不减掉,结论不成立。(09-09 原脚本的注释)
set -u
export VAR_GATE=0 TEX_GATE=0
cd /root/diffmvs
RUN () {
  ARM=$1; TAG=$2; SEED=$3; CKPT=$4
  OUT=/root/ms2/$ARM/$TAG
  [ -d "$OUT/depth_est" ] && [ "$(ls $OUT/depth_est 2>/dev/null | wc -l)" = "132" ] && { echo "SKIP $ARM/$TAG"; return; }
  mkdir -p "$OUT"
  /venv/main/bin/python -u test.py --dataset=general --batch_size=1 --num_view=10 \
    --method=casdiffmvs --save_depth --testpath=/root/mvs_P16k --testlist=/root/sp_testlist.txt \
    --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
    --loadckpt="$CKPT" --outdir="$OUT" --seed $SEED \
    --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --min_radius 0.125 --max_radius 8 \
    --photo_thres 0.3 0.5 0.5 --geo_mask_thres 2 --geo_pixel_thres 1.0 --geo_depth_thres 0.01 \
    > /root/ms2/$ARM.$TAG.log 2>&1 &
  PID=$!
  for i in $(seq 1 300); do
    n=$(ls "$OUT/depth_est"/*.pfm 2>/dev/null | wc -l)
    [ "$n" -ge 132 ] && break
    kill -0 $PID 2>/dev/null || break
    sleep 4
  done
  sleep 4
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
  echo "DONE $ARM/$TAG seed=$SEED  深度图 $(ls $OUT/depth_est/*.pfm 2>/dev/null | wc -l) 张"
}
BEF=/root/ckpt_src/casdiffmvs_mvgZeroDTU.ckpt
AFT=/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt
mkdir -p /root/ms2
for ARM_CK in "before:$BEF" "after:$AFT"; do
  ARM=${ARM_CK%%:*}; CK=${ARM_CK#*:}
  RUN $ARM floorA 123 "$CK"      # 噪声地板:同种子第一遍
  RUN $ARM floorB 123 "$CK"      # 噪声地板:同种子第二遍
  for s in 1 2 3 4 5 6; do RUN $ARM s$s $s "$CK"; done
done
echo "ALL DONE"
