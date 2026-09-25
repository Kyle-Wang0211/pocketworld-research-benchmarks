#!/bin/bash
# build_xr_propagate.sh —— 编外推工具。旗标 / 包含路径逐字取自 bkpose/build-mac/build.ninja 里
# xrslam-core 目标编 detail.cpp 那一条(FLAGS + INCLUDES),另加 xrslam-extra 与 yaml-cpp 头文件(YamlConfig)。
# 链接 bkpose/v/tap/libxrslam.dylib 的一份拷贝(同一 8ebac9a 源码构建,sha 与原件相同)。
set -euo pipefail
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
O=$SP/offline_sfm; X=$SP/bkpose/xrslam-wt; B=$SP/bkpose/build-mac; D=$HOME/Developer/xrslam-deps-tarballs
FLAGS=(-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY=0
       -DXRSLAM_FRONTEND_QUEUE_CAPACITY=0 -I$SP/bkpose/build-mac.ocv_shim -O3 -DNDEBUG -std=gnu++17 -arch arm64
       -Qunused-arguments -mllvm -inline-threshold=5000)
INC=(-I$X/xrslam/include -I$B/xrslam/include -I$X/xrslam/src -I$X/xrslam-extra/include -I$D/spdlog/include
     -I$D/yamlcpp/include -isystem $D/eigen-3.3.7 -isystem $B/_deps/depends-ceres-solver-build/config
     -isystem $D/ceres_pinned/internal/ceres/miniglog -isystem $D/ceres_pinned/include
     -isystem /opt/homebrew/Cellar/opencv/5.0.0_5/include/opencv5)
c++ "${FLAGS[@]}" "${INC[@]}" $O/tools/xr_propagate.cc -L$O/build/xrlib -lxrslam \
   -Wl,-rpath,$O/build/xrlib -Wl,-rpath,/opt/homebrew/opt/opencv/lib -o $O/build/xr_propagate
shasum -a 256 $O/build/xr_propagate $O/build/xrlib/libxrslam.dylib
