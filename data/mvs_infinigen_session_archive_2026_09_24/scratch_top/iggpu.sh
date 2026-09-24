#!/bin/bash
# GPU 空闲下重测一帧渲染成本(已定配置: 8192 采样 + 去噪, 768x576)。
# 对照: 09-22 训练占卡时同配置同分辨率实测 227 秒/帧。
# 🔴 configure_cycles_devices(use_gpu=True) 是默认值 => 之前那批计时很可能一直在抢卡。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
rm -rf /root/iggpu /root/igr/frames /root/frames
LOG "渲 1 帧 768x576 @8192+去噪, GPU 空闲"
T0=$(date +%s)
timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
  --input_folder /root/ig_probe/coarse --output_folder /root/iggpu \
  -g fast_solve.gin singleroom.gin \
  -p compose_indoors.terrain_enabled=False \
     configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
     render_image.render_resolution_override=[768,576] \
  > /root/iggpu.log 2>&1
T1=$(date +%s)
LOG "  脚本 $((T1-T0)) 秒   (对照: 训练占卡时 227 秒)"
echo "  Blender: $(grep -oE '^Time: [0-9:.]+' /root/iggpu.log | tail -1)  $(grep -oE 'Sample [0-9]+/[0-9]+' /root/iggpu.log | tail -1)"
echo "  === 它到底用了什么设备 ==="
grep -iE "device|OPTIX|CUDA|CPU-only|Job will use" /root/iggpu.log | head -6 | sed 's/^/    /'
touch /root/IGGPU_DONE
