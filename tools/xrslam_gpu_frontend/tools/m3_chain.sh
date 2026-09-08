#!/bin/bash
cd /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp && cmake --build build --target aether_lk_gpu_probe -j6 2>&1 | grep -E "error|Built target aether_lk" | head -8
echo "══ cpu-l0 (pad+pyrdown+scharr+LK, CLAHE from CPU) ══"; ./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440 --cpu-l0 2>&1 | grep -v "^\s*$" | head -20
echo "══ gpu end-to-end (dumps lut/res) ══"; ./build/aether_lk_gpu_probe /Users/kaidongwang/Developer/xrslam-gpu-detect/wgsl /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/img.u8 /Users/kaidongwang/Developer/xrslam-gpu-detect/out1920/m2_cv401 1920 1440 2>&1 | grep -E "^mode|^prev L0|^LK|rc=" 
echo "══ CLAHE 中间量对拍 ══"
cd /Users/kaidongwang/Developer/xrslam-gpu-detect && uv run --with numpy python3 tools/clahe_diag2.py 1920 1440 out1920/m2_cv401 out1920/img.u8 2>&1 | grep -v "^Installed\|^Resolved\|^Prepared\|^Downloaded"
echo M3_CHAIN_DONE
