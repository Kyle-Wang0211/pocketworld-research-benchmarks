#!/bin/bash
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake -S . -B build > /dev/null 2>&1; cmake --build build --target aether_fp_probe -j6 2>&1 | grep -E "error|Built target aether_fp" | head -5
./build/aether_fp_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl
echo FP_DONE
