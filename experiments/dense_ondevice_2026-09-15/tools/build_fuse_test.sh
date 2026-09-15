#!/bin/bash
# Host build of the Stage-2 fusion gate: same OpenCV 4.0.1 tree the iPhone product links, host build at
# ~/Developer/opencv-401-build-mac (CMAKE_CXX_FLAGS=-ffp-contract=off, WITH_LAPACK=OFF), same flags as the
# device archive (pocketworld android_ready/native/xrslam/build_generic_core.sh:127 -ffp-contract=off -fno-fast-math).
set -uo pipefail
SRC=$HOME/Developer/Aether3D-cross/aether_cpp/src/dense
OCVB=$HOME/Developer/opencv-401-build-mac; OCVS=$HOME/Developer/opencv-401-src
OUT=${1:-$PWD/test_fuse}
clang++ -std=c++20 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra \
  -I"$OCVB" -I"$OCVS/include" -I"$OCVS/modules/core/include" -I"$OCVS/modules/imgproc/include" \
  "$SRC/dense_fuse.cc" "$SRC/test_fuse.cc" -o "$OUT" \
  "$OCVB/lib/libopencv_imgproc.a" "$OCVB/lib/libopencv_core.a" -lz -framework Accelerate 2>&1 | grep -vE "^$" | head -40
[ -x "$OUT" ] && echo "BUILT $OUT" || { echo "BUILD_FAIL"; exit 1; }
