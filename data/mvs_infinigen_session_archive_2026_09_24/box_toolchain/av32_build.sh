#!/bin/bash
set -u
cd /root && rm -rf av32_build && mkdir av32_build && cd av32_build
cmake ../av32_src \
  -DALICEVISION_BUILD_DEPENDENCIES=ON -DALICEVISION_BUILD_TESTS=OFF \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/root/av32_prefix \
  -DAV_USE_CUDA=OFF -DAV_BUILD_CUDA=OFF -DAV_BUILD_OPENCV=OFF -DAV_BUILD_POPSIFT=OFF \
  -DAV_BUILD_CCTAG=OFF -DAV_BUILD_APRILTAG=OFF -DAV_BUILD_ONNXRUNTIME=OFF \
  -DAV_BUILD_PCL=OFF -DAV_BUILD_USD=OFF -DAV_BUILD_FFMPEG=OFF -DAV_BUILD_VPX=OFF \
  -DAV_BUILD_OPENGV=OFF > /root/av32_cmake.log 2>&1
echo "CMAKE-RC=$?"
make -j32 > /root/av32_make.log 2>&1
echo "MAKE-RC=$?"
find /root/av32_build /root/av32_prefix -name "aliceVision_meshing" -type f 2>/dev/null
