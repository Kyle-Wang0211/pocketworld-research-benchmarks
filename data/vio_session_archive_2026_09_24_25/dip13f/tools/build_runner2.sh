#!/bin/bash
set -e
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
X=xrslam-wt; D=$HOME/Developer/xrslam-deps-tarballs; B=build-inst; OUT=v/inst; IO=$X/xrslam-pc/player/src/IO
CXXFLAGS="-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY=0 -DXRSLAM_FRONTEND_QUEUE_CAPACITY=0 -I$B.ocv_shim"
c++ -std=c++17 -O2 $CXXFLAGS -o $OUT/pwvi_runner2 tools/pwvi_runner.cpp $IO/dataset_reader.cpp $IO/euroc_dataset_reader.cpp $IO/async_dataset_reader.cpp $IO/tum_dataset_reader.cpp -I$X/xrslam-interface/include -I$IO -I$X/xrslam-pc/player/src -I$X/xrslam-extra/include -I$X/xrslam/include -I$B/xrslam/include -I$D/eigen-3.3.7 -I$D/yamlcpp/include -I/opt/homebrew/opt/opencv/include/opencv5 -L$OUT -lxrslam -L/opt/homebrew/opt/opencv/lib -lopencv_core -lopencv_imgcodecs -lopencv_imgproc -Wl,-rpath,$PWD/$OUT -Wl,-rpath,/opt/homebrew/opt/opencv/lib
echo OK
