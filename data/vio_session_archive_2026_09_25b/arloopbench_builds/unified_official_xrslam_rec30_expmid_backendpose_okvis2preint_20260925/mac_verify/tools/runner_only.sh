#!/bin/bash
# runner_only.sh <src v/NAME> <new v/NAME> [runner defs]:沿用 src 目录里已编好的引擎 dylib(逐字节拷贝),只重编回放器。
set -euo pipefail
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/preint; X=$W/xrslam-wt; B=$W/build-mac-thrOFF; D=$HOME/Developer/xrslam-deps-tarballs
SRC=$W/v/$1; OUT=$W/v/$2; DEFS="${3:-}"
OCV_INC=/opt/homebrew/opt/opencv/include/opencv5; OCV_LIB=/opt/homebrew/opt/opencv/lib
CXXFLAGS="-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY=0 -DXRSLAM_FRONTEND_QUEUE_CAPACITY=0 -I$B.ocv_shim"
mkdir -p "$OUT"; cp "$SRC/libxrslam.dylib" "$OUT/"
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -DPW_BKPOSE_TAP $DEFS -o "$OUT/pwvi_runner" \
  "$W/tools/pwvi_runner.cpp" "$IO/dataset_reader.cpp" "$IO/euroc_dataset_reader.cpp" \
  "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" \
  -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" \
  -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$B/xrslam/include" \
  -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I"$OCV_INC" \
  -L"$OUT" -lxrslam -L"$OCV_LIB" -lopencv_core -lopencv_imgcodecs -lopencv_imgproc \
  -Wl,-rpath,"$OUT" -Wl,-rpath,"$OCV_LIB"
cmp "$SRC/libxrslam.dylib" "$OUT/libxrslam.dylib" && echo "RUNNER_OK $2 (引擎 dylib 与 $1 逐字节相同)"
