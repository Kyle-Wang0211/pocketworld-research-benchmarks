#!/bin/bash
set -u
cmake -S /root/av32_src/src -B /root/av32_build/external/aliceVision_build \
      -DALICEVISION_USE_ONNX=OFF -DALICEVISION_BUILD_SEGMENTATION=OFF \
      -DALICEVISION_REQUIRE_CERES_WITH_SUITESPARSE=OFF > /root/av32_av_cfg.log 2>&1
echo "AV-CFG-RC=$?"
tail -3 /root/av32_av_cfg.log
cd /root/av32_build && make -j32 > /root/av32_make7.log 2>&1
echo "MAKE7-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
