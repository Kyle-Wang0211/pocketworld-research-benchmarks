#!/bin/bash
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake -S . -B build > /dev/null 2>&1; cmake --build build --target aether_fp_probe aether_lk_gpu_probe -j6 2>&1 | grep -E "error|Built target aether" | head -8
echo "══ fp probe fast ══"; AETHER_STRICT_MATH=0 ./build/aether_fp_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl
echo "══ fp probe strict ══"; AETHER_STRICT_MATH=1 ./build/aether_fp_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl
for sm in 1 0; do echo "══ lk probe strict=$sm: gpu end-to-end ══"; AETHER_STRICT_MATH=$sm ./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440 2>&1 | grep -v "^\s*$" | head -12; done
echo STRICT_DONE
