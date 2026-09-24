#!/bin/bash
set -u
# AliceVision 3.2 src/CMakeLists.txt:392 calls find_package(ONNXRuntime) and the bundled
# cmake/FindONNXRuntime.cmake FATAL_ERRORs when it is absent.  ONNX is only used by the
# segmentation module, which meshing / meshFiltering do not touch, so disable both.
cmake -B /root/av32_build/external/aliceVision_build \
      -DALICEVISION_USE_ONNX=OFF -DALICEVISION_BUILD_SEGMENTATION=OFF > /root/av32_av_cfg.log 2>&1
echo "AV-CFG-RC=$?"
tail -5 /root/av32_av_cfg.log
cd /root/av32_build && make -j32 > /root/av32_make5.log 2>&1
echo "MAKE5-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
