#!/bin/bash
# build_xr_propagate2.sh —— 编新引擎外推工具(preint/xrslam-wt @4e8dda2,单线程构建 build-mac-thrOFF 的 detail.cpp 旗标)。
# 以下沿用旧版说明:旗标 / 包含路径逐字取自 bkpose/build-mac/build.ninja 里
# xrslam-core 目标编 detail.cpp 那一条(FLAGS + INCLUDES),另加 xrslam-extra 与 yaml-cpp 头文件(YamlConfig)。
# 链接 preint/v/okvis_cd_nothr/libxrslam.dylib 的一份拷贝(与回放用的是同一个库)。
set -euo pipefail
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
O=$SP/offline_sfm; X=$SP/preint/xrslam-wt; B=$SP/preint/build-mac-thrOFF; D=$HOME/Developer/xrslam-deps-tarballs
FLAGS=(-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY=0
       -DXRSLAM_FRONTEND_QUEUE_CAPACITY=0 -I$SP/preint/build-mac-thrOFF.ocv_shim -O3 -DNDEBUG -std=gnu++17 -arch arm64
       -Qunused-arguments -mllvm -inline-threshold=5000)
INC=(-I$X/xrslam/include -I$B/xrslam/include -I$X/xrslam/src -I$X/xrslam-extra/include -I$D/spdlog/include
     -I$D/yamlcpp/include -isystem $D/eigen-3.3.7 -isystem $B/_deps/depends-ceres-solver-build/config
     -isystem $D/ceres_pinned/internal/ceres/miniglog -isystem $D/ceres_pinned/include
     -isystem /opt/homebrew/Cellar/opencv/5.0.0_5/include/opencv5)
c++ "${FLAGS[@]}" "${INC[@]}" $O/tools/xr_propagate2.cc -L$O/build/xrlib2 -lxrslam \
   -Wl,-rpath,$O/build/xrlib2 -Wl,-rpath,/opt/homebrew/opt/opencv/lib -o $O/build/xr_propagate2
shasum -a 256 $O/build/xr_propagate2 $O/build/xrlib2/libxrslam.dylib
