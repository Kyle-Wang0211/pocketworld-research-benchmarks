#!/bin/bash
# Host build of the offline alignment checker (same recipe as step2/tools/build.sh "offline" step),
# linking the prebuilt host libpwofficial_core.a READ-ONLY instead of the deleted step2/build objects.
set -euo pipefail
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
F=$SP/fixB; S=$SP/step2/src/aether_cpp; TP=/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party
L=$TP/glomap_vendor/build-host-fullbench/libpwofficial_core.a
CORE_DEFS="-DAETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1 -DEIGEN_MPL2_ONLY -DGLOG_NO_ABBREVIATED_SEVERITIES -DGLOG_USE_GLOG_EXPORT -DGLOG_VERSION_MAJOR=0 -DGLOG_VERSION_MINOR=7 -DGLOMAP_CUDA_DISABLED -DVL_DISABLE_AVX -DVL_DISABLE_SSE2"
CORE_INC="-I$S/official_pipeline/include -I$S/include -I$S/third_party/glomap_vendor/colmap-src -I$S/third_party/glomap_vendor/poselib-src -I$S/third_party/glomap_vendor/stubs -I$TP/glog-install/include -I$TP/ceres/include -I$TP/ceres-build-ios/include -I$TP/ceres/config -I$TP/eigen-install/include/eigen3 -I/opt/homebrew/include"
/usr/bin/c++ $CORE_DEFS $CORE_INC -I$S/official_pipeline/src -O3 -DNDEBUG -std=gnu++17 -arch arm64 -fPIE -w \
  $F/tools/device_align_offline.cc $L /opt/homebrew/lib/libceres.dylib /opt/homebrew/lib/libglog.dylib -lsqlite3 \
  -o $F/build/device_align_offline
ls -la $F/build/device_align_offline
