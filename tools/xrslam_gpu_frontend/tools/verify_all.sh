#!/bin/bash
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake --build build --target aether_gftt_gpu_probe aether_lk_gpu_probe -j6 2>&1 | grep -E "error|Built target aether" | head -6
INC="-I/Users/kaidongwang/Developer/opencv-401-build-mac -I/Users/kaidongwang/Developer/opencv-401-src/include"; for m in core imgproc video features2d flann; do INC="$INC -I/Users/kaidongwang/Developer/opencv-401-src/modules/$m/include"; done
clang++ -std=c++11 -O2 -ffp-contract=off -o /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/gftt_cpu_ref2_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/gftt_cpu_ref2.cpp $INC /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_features2d.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_flann.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_imgproc.a /Users/kaidongwang/Developer/opencv-401-build-mac/lib/libopencv_core.a -lz -framework Foundation -framework Accelerate 2>&1 | grep -E "error|Undefined" | head -5
mkdir -p /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401
echo "══ 4.0.1 GFTT 参照: CLAHE 后图 (XRSLAM 真路径, max 150) ══"; /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/gftt_cpu_ref2_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/prev_clahe.u8 1920 1440 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe 150
echo "  detector vs goodFeaturesToTrack 集合: $(python3 -c "
a=set(tuple(l.split()[:2]) for l in open('/Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe/corners_cpu.txt')); b=set(tuple(l.split()[:2]) for l in open('/Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe/gftt_detector.txt')); c=set(tuple(str(int(float(v))) for v in l.split()[:2]) for l in open('/Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401/gftt_clahe.txt')); print(len(a),len(b),len(a&b),'xrslam-path',len(c),len(a&c))")"
echo "══ 4.0.1 GFTT 参照: 原图 (对照 5.0 产的 out1920, max 200) ══"; /Users/kaidongwang/Developer/xrslam-gpu-detect/tools/gftt_cpu_ref2_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 1920 1440 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401 200
cmp /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401/eig.f32 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/eig.f32 && echo "  eig.f32 4.0.1 == 5.0 逐字节" || echo "  eig.f32 差: $(cmp -l /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401/eig.f32 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/eig.f32 | wc -l) 字节"
diff -q /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401/corners_cpu.txt /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/corners_cpu.txt && echo "  corners 4.0.1 == 5.0" || echo "  corners 4.0.1 != 5.0"
for sm in 1 0; do
  echo "══ strict=$sm ══"
  AETHER_STRICT_MATH=$sm ./build/aether_gftt_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe 1920 1440 150 | grep -E "^eig|match"
  AETHER_STRICT_MATH=$sm ./build/aether_gftt_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_401 1920 1440 200 | grep -E "match"
  AETHER_STRICT_MATH=$sm ./build/aether_gftt_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out 752 480 | grep -E "match"
  AETHER_STRICT_MATH=$sm ./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440 2>&1 | grep -E "mismatches=[1-9]|^LK|rc="
done
echo VERIFY_DONE
