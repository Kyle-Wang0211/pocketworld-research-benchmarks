#!/bin/bash
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake --build build --target aether_gpufe_selftest aether_lk_gpu_probe -j6 2>&1 | grep -E "error|Built target aether_gpufe|Built target aether_lk" | head -10
echo "══ selftest (fast math default) ══"; ./build/aether_gpufe_selftest /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920_clahe 1920 1440
echo "══ lk probe end-to-end (packed src) ══"; ./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440 2>&1 | grep -E "mismatches=[1-9]|^LK|rc="
echo GPUFE_DONE
