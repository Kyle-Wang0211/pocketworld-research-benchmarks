#!/bin/bash
# 2026-09-09: rebuilds the engine build tree that the 09-08 disk cleanup destroyed.
# Every option here is recovered from libxrslam_gpufe_4beb1a9.receipt.json (compile_flags, threading,
# xrslam_ios, ceres_namespace, gpu_frontend) - not guessed. The gate on this being faithful is that
# the 56 unchanged archive members must come out byte-identical to the old archive.
set -euo pipefail
X=$HOME/Developer/xrslam-4beb1a9-thr
A=$HOME/Developer/Aether3D-cross/aether_cpp
DEPS=$HOME/Developer/xrslam-deps-tarballs
B=$X/build-cleanA
[ -d "$DEPS/eigen-3.3.7" ] || { echo "missing eigen 3.3.7"; exit 1; }
[ -d "$DEPS/opencv-4.0.1-ios-framework" ] || { echo "missing opencv 4.0.1 ios framework (extract the zip)"; exit 1; }
cmake -S "$X" -B "$B" -G Ninja \
  -D CMAKE_MAKE_PROGRAM="$(command -v ninja || echo /opt/homebrew/bin/ninja)" \
  -D CMAKE_TOOLCHAIN_FILE="$X/cmake/Modules/Platform/ios.toolchain.cmake" \
  -D CMAKE_BUILD_TYPE=Release \
  -D IOS_PLATFORM=OS64 -D IOS_ARCH=arm64 -D IOS_DEPLOYMENT_TARGET=14.0 \
  -D ENABLE_BITCODE=0 -D ENABLE_ARC=1 -D ENABLE_VISIBILITY=0 \
  -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -D XRSLAM_IOS_OVERRIDE=1 \
  -D XRSLAM_THREADING_OVERRIDE=1 -D XRSLAM_ENABLE_THREADING=ON \
  -D XRSLAM_GPU_FRONTEND=ON -D PW_GPU_FRONTEND_INCLUDE_DIR="$A/tools" \
  -D CMAKE_CXX_FLAGS="-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-EIGEN="$DEPS/eigen-3.3.7" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-OPENCV="$DEPS/opencv-4.0.1-ios-framework/opencv2.framework" \
  -D FETCHCONTENT_FULLY_DISCONNECTED=OFF
cmake --build "$B" -j8
