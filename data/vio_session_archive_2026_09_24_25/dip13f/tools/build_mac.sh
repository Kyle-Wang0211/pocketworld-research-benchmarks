#!/bin/bash
# build_mac.sh <name> <lowlatency ON|OFF> <threading ON|OFF> [queue_cap 0|default]
# Same recipe as scaleS2/tools/build_variant.sh (itself = xrslam pw_tools/regression/build_pc_headless.sh @04c0e83),
# source = xrofficial/xrslam-wt (feat/official-ios-rules), production compile flags (-fno-fast-math).
set -euo pipefail
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
X=$W/xrslam-wt
NAME="$1"; LL="$2"; THR="$3"; CAP="${4:-0}"
B=$W/build-$NAME; OUT=$W/v/$NAME
D=$HOME/Developer/xrslam-deps-tarballs
STUBS=$W/../scaleS3/stubs
OCV=/opt/homebrew/lib/cmake/opencv5
OCV_INC=/opt/homebrew/opt/opencv/include/opencv5
OCV_LIB=/opt/homebrew/opt/opencv/lib
CXXFLAGS="-ffp-contract=off -fno-fast-math -fchar8_t -Dceres=pw_xrslam_ceres_1_14"
if [ "$CAP" = 0 ]; then
  # official upstream: worker queues unbounded (worker.h: capacity 0 == upstream behaviour)
  CXXFLAGS="$CXXFLAGS -DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY=0 -DXRSLAM_FRONTEND_QUEUE_CAPACITY=0"
fi
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
rm -f "$X/lib/libxrslam.dylib"
cmake -S "$X" -B "$B" -G Ninja \
  -D CMAKE_BUILD_TYPE=Release -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -D XRSLAM_ENABLE_THREADING=$THR -D XRSLAM_LOWLATENCY_POSE=$LL \
  -D SUITESPARSE=OFF -D CXSPARSE=OFF -D EIGENSPARSE=ON \
  -D CMAKE_CXX_FLAGS="$CXXFLAGS" \
  -D OpenCV_DIR="$OCV" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-EIGEN="$D/eigen-3.3.7" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-CERES-SOLVER="$D/ceres_pinned" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-SPDLOG="$D/spdlog" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-YAML-CPP="$D/yamlcpp" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-ARGPARSE="$STUBS/argparse" \
  -D FETCHCONTENT_SOURCE_DIR_DEPENDS-LITEVIZ="$STUBS/liteviz" \
  -D FETCHCONTENT_FULLY_DISCONNECTED=ON > "$B.configure.log" 2>&1 \
  || { echo "configure FAIL $B.configure.log"; tail -30 "$B.configure.log"; exit 1; }
ninja -C "$B" -j "${JOBS:-6}" xrslam > "$B.build.log" 2>&1 \
  || { echo "build FAIL $B.build.log"; tail -30 "$B.build.log"; exit 1; }
mkdir -p "$OUT"; cp "$X/lib/libxrslam.dylib" "$OUT/"
install_name_tool -id "@rpath/libxrslam.dylib" "$OUT/libxrslam.dylib" 2>/dev/null || true
IO="$X/xrslam-pc/player/src/IO"
c++ -std=c++17 -O2 $CXXFLAGS -o "$OUT/pwvi_runner" \
  "$W/tools/pwvi_runner.cpp" "$IO/dataset_reader.cpp" "$IO/euroc_dataset_reader.cpp" \
  "$IO/async_dataset_reader.cpp" "$IO/tum_dataset_reader.cpp" \
  -I"$X/xrslam-interface/include" -I"$IO" -I"$X/xrslam-pc/player/src" \
  -I"$X/xrslam-extra/include" -I"$X/xrslam/include" -I"$B/xrslam/include" \
  -I"$D/eigen-3.3.7" -I"$D/yamlcpp/include" -I"$OCV_INC" \
  -L"$OUT" -lxrslam \
  -L"$OCV_LIB" -lopencv_core -lopencv_imgcodecs -lopencv_imgproc \
  -Wl,-rpath,"$OUT" -Wl,-rpath,"$OCV_LIB"
grep -n "XRSLAM_IOS\|THREADING\|LOWLATENCY" "$B/xrslam/include/xrslam/version.h" || true
echo "BUILD_OK $NAME"; shasum -a 256 "$OUT/libxrslam.dylib" "$OUT/pwvi_runner"
