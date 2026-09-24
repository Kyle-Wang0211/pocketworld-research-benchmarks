#!/bin/bash
# 「官方配方, 正确地, 在世界标准尺度上跑一次」
#   分辨率 2048x1536 —— 4032x3024 在 base-32 网格上的【精确 4:3】档 (scale_w == scale_h),
#     且 = BlendedMVS 高分辨率版分辨率, = 训练 768 的 2.67x, 落在官方测试惯例 (2.1-2.5x) 上沿。
#   融合 geo_mask_thres = 1 —— 官方 ETH3D 逐场景表 (test.py:237-263) 25 个场景里 24 个是 1;
#     我们此前一直用 2-3, 那是 argparse 默认值不是官方值。
#   像素闸 = 2.6667 (= 2048/768), 与 768@1.0 物理等价。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
CKPT=/root/diffmvs_full/checkpoints/casdiff_full/model_000000.ckpt
D=/root/arm_ep0_2048
rm -rf $D
LOG "推理 2048x1536"
bash /root/infer_res.sh "$CKPT" "$D" 1536 2048 2>&1 | tail -3
LOG "自证分辨率"
/venv/main/bin/python -c "
import sys; sys.path.insert(0,/root/diffmvs)
from datasets.data_io import read_pfm; import numpy as np
a=np.array(read_pfm(/depth_est/00000000.pfm)[0]); print( depth_est, a.shape)
sw=a.shape[1]/4032.0; sh=a.shape[0]/3024.0
print( scale_w=%.6f scale_h=%.6f 各向同性=%s % (sw,sh,abs(sw-sh)<1e-9))
"
LOG "融合 thres=1 px=2.6667 (官方口径)"
/venv/main/bin/python /root/fuse_px.py $D 1 /root/t1_2048.ply 2.6667 2>&1 | tail -1
LOG "转 bin + 覆盖率"
/venv/main/bin/python /root/ply2bins.py /root/t1_2048.ply /root/bins_gate T1_2048 2>&1 | tail -1
touch /root/A2048_DONE
