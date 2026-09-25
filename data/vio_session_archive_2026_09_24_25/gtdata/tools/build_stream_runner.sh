#!/bin/bash
# build_stream_runner.sh S|M : same runner source + same IO sources as the lineage's own runner,
# only euroc_dataset_reader.cpp swapped for the stream-patched copy (read_image source of pixels).
set -euo pipefail
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
L=$1; X=$W/xrslam-wt-$L; B=$W/work/build-$L; D=$HOME/Developer/xrslam-deps-tarballs
OCV_INC=/opt/homebrew/opt/opencv/include/opencv5; OCV_LIB=/opt/homebrew/opt/opencv/lib
CXXFLAGS="-ffp-contract=off -fno-fast-math -Dceres=pw_xrslam_ceres_1_14"
if [ $L = S ]; then CXXFLAGS="$CXXFLAGS -fchar8_t -I$B.ocv_shim"; LIBDIR=$X/lib; else LIBDIR=$B/xrslam-interface; fi
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -o "$B/pw_euroc_runner_stream" \
  "$X/pw_tools/regression/euroc_runner.cpp" "$IO/dataset_reader.cpp" "$W/tools/euroc_dataset_reader_stream.cpp" \
  "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" \
  -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" \
  -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$B/xrslam/include" \
  -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I"$OCV_INC" \
  -L"$LIBDIR" -lxrslam -L"$OCV_LIB" -lopencv_core -lopencv_imgcodecs -lopencv_imgproc \
  -Wl,-rpath,"$LIBDIR" -Wl,-rpath,"$OCV_LIB"
echo BUILD_OK $B/pw_euroc_runner_stream
