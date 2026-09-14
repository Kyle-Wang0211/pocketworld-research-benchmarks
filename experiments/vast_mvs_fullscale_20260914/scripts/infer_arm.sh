#!/bin/bash
# ============================================================================
# 单臂推理 —— 唯一可变的是权重。其余每一项都写死在这里,任何一臂都跑这个脚本。
#   用法: ./infer_arm.sh <ckpt路径> <输出目录>
#
# 口径 = 「ETH3D 档 + filter.py 原生默认」,与历史对照臂 off768_true 完全一致
# (故可直接接上历史覆盖率表)。逐项出处:
#   --num_view=10                官方 test_eth_casdiffmvs.sh:10
#   --numdepth_initial=48        官方 test_eth_casdiffmvs.sh:11 (DTU:14 同; 只有 Tank 用 96)
#   --numdepth=384               三份官方脚本一致
#   --scale 0.0 0.125 0.025      官方 test_eth_casdiffmvs.sh:13 (Tank:14 同)
#   --sampling_timesteps/--ddim_eta/--stage_iters/--cost_dim_stage/--CostNum
#   --hidden_dim/--context_dim/--unet_dim/--min_radius/--max_radius
#                                三份官方脚本完全一致
#   --photo_thres 0.3 0.5 0.5    官方 test_eth_casdiffmvs.sh:17
#   --geo_mask_thres 2           官方三份脚本的有效值【全是 2】: DTU line20 显式 2;
#                                Tank/ETH3D 不传 -> test.py argparse 默认 2。
#                                filter.py:113 签名里的 3 是死代码: test.py:356-365 调用时
#                                总是显式传 args.geo_mask_thres, 那个 3 永不生效。
#                                (旧臂 off768_true 传的 3 不是官方值, 不照抄)
#   --geo_pixel_thres 1.0        test.py argparse 默认 (ETH3D/Tank 脚本都不覆盖)
#   --geo_depth_thres 0.01       三份官方脚本一致
#   --max_h 576 --max_w 768      我们的训练/推理分辨率
#   --testpath /root/mvs_P16k    同一批 132 张真实照片 + 同一份 pair.txt
# ============================================================================
set -euo pipefail
# filter.py 相对官方 HEAD(cd10d5c) 有 32 行本地改动: 两个【默认关闭】的实验旁路门
# (VAR_GATE 种子方差门 / TEX_GATE 纹理门), 代码是 `if _VAR_GATE > 0:` / `if _TEX_GATE > 0:`,
# 置 0 即走官方原逻辑。这里显式钉死, 任何一臂都不可能意外开启。
export VAR_GATE=0 TEX_GATE=0
CKPT="$1"; OUT="$2"
[ -f "$CKPT" ] || { echo "权重不存在: $CKPT"; exit 1; }
echo "[arm] VAR_GATE=$VAR_GATE TEX_GATE=$TEX_GATE (0=官方原逻辑)"
echo "[arm] ckpt=$CKPT  md5=$(md5sum "$CKPT" | cut -c1-14)  out=$OUT"
cd /root/diffmvs
exec /venv/main/bin/python -u test.py \
  --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=/root/mvs_P16k --testlist=/root/sp_testlist.txt \
  --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
  --loadckpt="$CKPT" --outdir="$OUT" \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 2 --geo_pixel_thres 1.0 --geo_depth_thres 0.01
