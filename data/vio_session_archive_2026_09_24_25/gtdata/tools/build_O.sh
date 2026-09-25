#!/bin/bash
# Official arm on the S lineage: xrslam 04c0e83 built exactly like S2's `official` variant
# (scaleS2/tools/build_variant.sh official ON 1 1): THREADING=ON, -DXRSLAM_IOS (the official iOS build's
# macro: sliding_window_tracker.cpp keyframe rule, frontend_worker, feature_tracker, yaml_config reads
# CONTENT), official iOS toolchain flags -ffast-math.  Runner = S2's euroc_runner.cpp (--pace, --camera-out,
# yaml content under XRSLAM_IOS) + our stream-patched euroc_dataset_reader.cpp.
set -euo pipefail
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
X=$W/xrslam-wt-O; B=$W/work/build-O; D=$HOME/Developer/xrslam-deps-tarballs; STUBS=$W/tools/stubs
OCV=/opt/homebrew/lib/cmake/opencv5; OCV_INC=/opt/homebrew/opt/opencv/include/opencv5; OCV_LIB=/opt/homebrew/opt/opencv/lib
CXXFLAGS="-ffast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14 -DXRSLAM_IOS"
SHIM="$B.ocv_shim"; mkdir -p "$SHIM/opencv2/calib3d"
cat > "$SHIM/opencv2/calib3d/calib3d_c.h" <<'H'
#ifndef PW_CALIB3D_C_SHIM_H
#define PW_CALIB3D_C_SHIM_H
#include <opencv2/calib3d.hpp>
#ifndef CV_EPNP
#define CV_EPNP cv::SOLVEPNP_EPNP
#endif
#endif
H
CXXFLAGS="$CXXFLAGS -I$SHIM"
cmake -S "$X" -B "$B" -G Ninja -D CMAKE_BUILD_TYPE=Release -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -D XRSLAM_ENABLE_THREADING=ON -D SUITESPARSE=OFF -D CXSPARSE=OFF -D EIGENSPARSE=ON \
  -D CMAKE_CXX_FLAGS="$CXXFLAGS" -D OpenCV_DIR="$OCV" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-EIGEN="$D/eigen-3.3.7" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-CERES-SOLVER="$D/ceres_pinned" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-SPDLOG="$D/spdlog" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-YAML-CPP="$D/yamlcpp" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-ARGPARSE="$STUBS/argparse" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-LITEVIZ="$STUBS/liteviz" \
  -D FETCHCONTENT_FULLY_DISCONNECTED=ON > "$B.configure.log" 2>&1 || { echo configure FAIL; tail -20 "$B.configure.log"; exit 1; }
ninja -C "$B" -j 6 xrslam > "$B.build.log" 2>&1 || { echo build FAIL; tail -30 "$B.build.log"; exit 1; }
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -o "$B/pw_euroc_runner_stream" \
  "$W/tools/euroc_runner_S2official.cpp" "$IO/dataset_reader.cpp" "$W/tools/euroc_dataset_reader_stream.cpp" \
  "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" \
  -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" \
  -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$B/xrslam/include" \
  -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I"$OCV_INC" \
  -L"$X/lib" -lxrslam -L"$OCV_LIB" -lopencv_core -lopencv_imgcodecs -lopencv_imgproc \
  -Wl,-rpath,"$X/lib" -Wl,-rpath,"$OCV_LIB"
grep -n "XRSLAM_IOS\|THREADING" "$B/xrslam/include/xrslam/version.h" || true
echo BUILD_OK; shasum -a 256 "$X/lib/libxrslam.dylib" "$B/pw_euroc_runner_stream"
