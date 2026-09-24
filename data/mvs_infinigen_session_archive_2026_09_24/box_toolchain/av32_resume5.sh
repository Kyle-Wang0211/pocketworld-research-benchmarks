#!/bin/bash
set -u
cmake -S /root/av32_src/src -B /root/av32_build/external/aliceVision_build \
      -DALICEVISION_USE_ONNX=OFF -DALICEVISION_BUILD_SEGMENTATION=OFF > /root/av32_av_cfg.log 2>&1
echo "AV-CFG-RC=$?"
tail -4 /root/av32_av_cfg.log
cd /root/av32_build && make -j32 > /root/av32_make6.log 2>&1
echo "MAKE6-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
