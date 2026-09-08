#!/bin/bash
set -x
while ! grep -q CHAIN_DONE /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_chain.log 2>/dev/null; do sleep 15; done
sed -i '' 's/-DWITH_ADE=OFF/-DWITH_ADE=OFF -DWITH_CAROTENE=OFF/' ~/Developer/opencv-401-build-mac.sh
rm -rf /Users/kaidongwang/Developer/opencv-401-build-mac; ~/Developer/opencv-401-build-mac.sh > ~/Developer/opencv-401-build-mac.log 2>&1; grep -E "BUILD_RC" ~/Developer/opencv-401-build-mac.log
grep -E "^WITH_CAROTENE" /Users/kaidongwang/Developer/opencv-401-build-mac/CMakeCache.txt; ls /Users/kaidongwang/Developer/opencv-401-build-mac/3rdparty/lib 2>/dev/null; echo "carotene symbols in core: $(nm /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_imgproc.a | grep -ci carotene)"
INC="-I/Users/kaidongwang/Developer/opencv-401-build-mac -I/Users/kaidongwang/Developer/opencv-401-src/include"; for m in core imgproc video features2d flann; do INC="$INC -I/Users/kaidongwang/Developer/opencv-401-src/modules/$m/include"; done
clang++ -std=c++11 -O2 -o /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref.cpp $INC   /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_video.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_features2d.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_flann.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_imgproc.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_core.a   $(ls /Users/kaidongwang/Developer/opencv-401-build-mac/3rdparty/lib/*.a 2>/dev/null) -lz -framework Foundation -framework Accelerate 2>&1 | grep -E "error|Undefined|symbol" | head -10
mkdir -p /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401nc
/Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref_cv401 1920 1440 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401nc /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv5/next_raw.u8
echo "══ cv401(carotene) vs cv401nc(no carotene) ══"
for f in prev_clahe.u8 prev_L0_pad.u8 prev_L1_pad.u8 prev_L3_pad.u8 prev_D0_pad.i16x2 gftt_clahe.txt lk_cpu.txt; do
  if cmp -s /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/$f /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401nc/$f; then echo "same  $f"; else echo "DIFF  $f ($(cmp -l /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/$f /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401nc/$f 2>/dev/null | wc -l) bytes)"; fi; done
echo "══ GPU probe vs cv401nc ══"
/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401nc 1920 1440
echo CHAIN2_DONE
