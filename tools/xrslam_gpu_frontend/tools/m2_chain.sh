#!/bin/bash
set -x
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake -S . -B build > /dev/null 2>&1; echo "configure rc=$?"
cmake --build build --target aether_lk_gpu_probe -j6 2>&1 | grep -E "error|Built target aether_lk" | head -8
echo "══ GPU probe vs cv5 dumps ══"
./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv5 1920 1440
echo "══ link lk_cpu_ref against 4.0.1 ══"
INC="-I/Users/kaidongwang/Developer/opencv-401-build-mac -I/Users/kaidongwang/Developer/opencv-401-src/include"; for m in core imgproc video features2d flann; do INC="$INC -I/Users/kaidongwang/Developer/opencv-401-src/modules/$m/include"; done
clang++ -std=c++11 -O2 -o /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref.cpp $INC   /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_video.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_features2d.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_flann.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_imgproc.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_core.a   $(ls /Users/kaidongwang/Developer/opencv-401-build-mac/3rdparty/lib/*.a 2>/dev/null) -lz -framework Foundation -framework Accelerate 2>&1 | grep -E "error|Undefined|symbol" | head -10
mkdir -p /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401
/Users/kaidongwang/Developer/xrslam-gpu-detect/tools/lk_cpu_ref_cv401 1920 1440 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv5/next_raw.u8
echo "══ cv5 vs cv401 dump 差异 (同一输入) ══"
for f in prev_clahe.u8 next_clahe.u8 prev_L0_pad.u8 prev_L1_pad.u8 prev_L2_pad.u8 prev_L3_pad.u8 prev_D0_pad.i16x2 prev_D3_pad.i16x2 gftt_clahe.txt lk_cpu.txt; do
  if cmp -s /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv5/$f /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/$f; then echo "same  $f"; else echo "DIFF  $f ($(cmp -l /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv5/$f /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/$f 2>/dev/null | wc -l) bytes)"; fi; done
echo "══ GPU probe vs cv401 dumps ══"
/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440
echo CHAIN_DONE
