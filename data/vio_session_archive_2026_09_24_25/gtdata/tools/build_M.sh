#!/bin/bash
# M lineage (pw/vio 1fe750c, Ceres 2.2 / OpenCV 5) headless build.
# Cache flags copied from the main tree's build-pc/CMakeCache.txt, which produced the M-lineage
# numbers of 09-22 (/tmp/pw_euroc_new -> ~/Developer/xrslam/lib/libxrslam.dylib):
#   Release, -ffp-contract=off -fno-fast-math -Dceres=pw_xrslam_ceres_1_14, THREADING=OFF,
#   CONFIG_FROM_STRING=ON, LOWLATENCY_POSE=ON, DEBUG=ON, DEBUG_INSPECTION=ON, VISUAL_LOCALIZATION=OFF,
#   eigen-3.3.7 + ceres-2.2.0 local tarballs.  Only deviation: XRSLAM_PC=OFF (player/GUI not needed;
#   pw/vio made it a real option that only gates add_subdirectory(xrslam-pc)).
set -euo pipefail
X="$1"; B="$2"
D="$HOME/Developer/xrslam-deps-tarballs"
OCV_INC=/opt/homebrew/opt/opencv/include/opencv5; OCV_LIB=/opt/homebrew/opt/opencv/lib
CXXFLAGS="-ffp-contract=off -fno-fast-math -Dceres=pw_xrslam_ceres_1_14"
cmake -S "$X" -B "$B" -G Ninja \
  -D CMAKE_BUILD_TYPE=Release -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -D XRSLAM_ENABLE_THREADING=OFF -D XRSLAM_CONFIG_FROM_STRING=ON -D XRSLAM_LOWLATENCY_POSE=ON \
  -D XRSLAM_DEBUG=ON -D XRSLAM_ENABLE_DEBUG_INSPECTION=ON -D XRSLAM_ENABLE_VISUAL_LOCALIZATION=OFF \
  -D XRSLAM_PC=OFF -D XRSLAM_TEST=OFF \
  -D CMAKE_CXX_FLAGS="$CXXFLAGS" -D OpenCV_DIR=/opt/homebrew/lib/cmake/opencv5 \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-EIGEN="$D/eigen-3.3.7" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-CERES-SOLVER="$D/ceres-2.2.0" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-SPDLOG="$D/spdlog" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-YAML-CPP="$D/yamlcpp" \
  -D FETCHCONTENT_FULLY_DISCONNECTED=ON > "$B.configure.log" 2>&1 \
  || { echo "configure failed"; tail -30 "$B.configure.log"; exit 1; }
ninja -C "$B" -j "${JOBS:-6}" xrslam > "$B.build.log" 2>&1 || { echo "build failed"; tail -30 "$B.build.log"; exit 1; }
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -o "$B/pw_euroc_runner" \
  "$X/pw_tools/regression/euroc_runner.cpp" "$IO/dataset_reader.cpp" "$IO/euroc_dataset_reader.cpp" \
  "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" \
  -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" \
  -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$B/xrslam/include" \
  -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I"$OCV_INC" \
  -L"$B/xrslam-interface" -lxrslam -L"$OCV_LIB" -lopencv_core -lopencv_imgcodecs -lopencv_imgproc \
  -Wl,-rpath,"$B/xrslam-interface" -Wl,-rpath,"$OCV_LIB"
echo "BUILD_OK $B/pw_euroc_runner"
shasum -a 256 "$B/xrslam-interface/libxrslam.dylib" "$B/pw_euroc_runner"
