#!/bin/bash
set -e
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb; W=/Users/kaidongwang/Developer/xrslam-wt/solver-budget; X=$S/base-04c0e83; D=$HOME/Developer/xrslam-deps-tarballs
mkdir -p $S/build-basenr
CXXFLAGS="-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -I$S/build-base.ocv_shim"
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -o "$S/build-basenr/pw_euroc_runner" "$W/pw_tools/regression/euroc_runner.cpp" "$IO/dataset_reader.cpp" "$IO/euroc_dataset_reader.cpp" "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$S/build-base/xrslam/include" -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I/opt/homebrew/opt/opencv/include/opencv5 -L"$X/lib" -lxrslam -L/opt/homebrew/opt/opencv/lib -lopencv_core -lopencv_imgcodecs -lopencv_imgproc -Wl,-rpath,"$X/lib" -Wl,-rpath,/opt/homebrew/opt/opencv/lib
otool -L $S/build-basenr/pw_euroc_runner | grep xrslam
