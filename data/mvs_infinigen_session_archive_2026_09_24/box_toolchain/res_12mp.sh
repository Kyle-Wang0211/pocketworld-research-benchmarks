#!/bin/bash
# ep0 权重一个字节不动, 只把推理分辨率从 768x576 换成【原生】。
# 官方 test.py 默认 max_h=4800 max_w=6400, 三份官方测试脚本都不覆盖 => 官方就是跑原生。
# 4032/32=126 整除; 3024 向下取整到 32 倍数 = 3008 (datasets/mvs.py:112 base=32)。
# 内参由 scale_img_adaptive 自动跟着缩 (intrinsics[0,:]*=scale_w, [1,:]*=scale_h)。
# 融合 thres=3, 与所有既有臂同口径。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
D=/root/arm_ep0_12mp
if [ "$(ls $D/depth_est 2>/dev/null | wc -l)" != "132" ]; then
  LOG "推理 4032x3008 (27.4x 像素)"
  /root/infer_res.sh /root/snap_ckpt/full_ep0.ckpt $D 3008 4032 > /root/12mp.infer.log 2>&1
  LOG "  rc=$? depth=$(ls $D/depth_est 2>/dev/null | wc -l)"
fi
if [ ! -f $D/pc_t3.ply ]; then
  LOG "融合 thres=3"
  /venv/main/bin/python /root/fuse_only.py $D 3 $D/pc_t3.ply > /root/12mp.fuse.log 2>&1
  LOG "  rc=$?  $(ls -la $D/pc_t3.ply 2>/dev/null | awk "{print \$5}") 字节"
fi
LOG "完成"; touch /root/RES.DONE
