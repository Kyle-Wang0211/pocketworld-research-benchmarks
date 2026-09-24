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
#   --geo_mask_thres 2           🔴 2026-09-22 更正: 原注释写「官方三份脚本的有效值全是 2」,
#                                这是假的, 我没核就写了。逐行核 test.py(cd10d5c) 的实情:
#                                  DTU   test.py:314-326  filter_depth(..., args.geo_mask_thres=2,
#                                                          args.geo_pixel_thres=0.125)  <- 脚本 line20 显式传
#                                  Tank  test.py:327-337  filter_depth_dynamic(...) 【是另一个函数】,
#                                                          只吃 photo_thres_all[scan]; 这两个参数根本不参与
#                                  ETH3D test.py:338-351  filter_depth(..., geo_mask_thres_all[scan],
#                                                          geo_pixel_thres_all[scan])  <- 逐场景表【覆盖 argparse】,
#                                                          官方 test_eth_*.sh 压根不传这两个参数
#                                  表值 test.py:237-263: geo_mask_thres 25 个场景里 24 个是 1(只 bridge=2)
#                                  我们  test.py:353-366  dataset=general -> 用 args.*, 两张表对我们全不生效
#                                ⇒ 官方没有统一值: DTU=2, ETH3D=1, Tank 不适用。
#                                ⇒ 为什么仍然取 2 而不抄 ETH3D 的 1: 见下「闸梯子」一节 —— 抄 1 在我们的
#                                  素材上多层显著变重, 而 ETH3D 用的 F1 会奖励完整度, 我们的判据不会。
#   --geo_pixel_thres 1.0        🔴 同上更正: 不存在「官方默认」这回事。DTU 脚本显式传 0.125;
#                                ETH3D 走逐场景表, 取值 0.5 / 1 / 2 (室内 office/lounge/old_computer 取 2,
#                                living_room/lecture_room/exhibition_hall 取 0.5)。1.0 是表里 9/25 个场景的值,
#                                但绝不是「大家都用的那个数」。官方做法本身就是【逐场景调】。
#
#   闸梯子 (2026-09-22 实测, 同一份 lg_ep0 深度图, 唯一变量 geo_mask_thres, geo_pixel_thres 恒 1.0):
#       thres=3  36,233,955 点 | 厚度中位 69.0mm | 多层(片>=1000) 56.96%
#       thres=2  39,345,336 点 | 厚度中位 83.2mm | 多层(片>=1000) 61.99%   <- 本脚本
#       thres=1  42,007,356 点 | 厚度中位111.0mm | 多层(片>=1000) 70.86%   <- ETH3D 官方表值
#     配对比较(只算三臂【公共像素】, 消掉覆盖面差异)同向: >2cm 多层 43.59 / 49.09 / 56.43%
#     ⇒ 松闸买到的 +16% 点数, 代价是同一批像素上第二层更密更连片。用户肉眼已独立判过
#       「thres=1 比 thres=3 多层和粘连都增加」(/root/holdout.sh)。故【不抄 ETH3D 的 1】。
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
