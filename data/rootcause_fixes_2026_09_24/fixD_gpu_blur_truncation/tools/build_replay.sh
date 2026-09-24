#!/bin/bash
# build_replay.sh — fixD replay driver = step2 driver (+CG decode, +env GPU extract) linked against the SHIPPING core
# objects (sfmB build of 7dc00642+pw 4e22ee7, copied to build/coreobj) + the shipped GPU extractor carrier sources
# (568f53d3, WGSL byte-identical to libpwofficial_gpu_extract.a) with the fixD fault-injection hook (FI_SPEC/FI_FRAME).
set -euo pipefail
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sfmB
S=$B/src/aether_cpp; PW=$B/src/pw_vendor_4e22ee7; TP=/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party
GPUOBJ=${1:-$W/build/gpufiobj}; OUT=${2:-$W/build/fixd_replay_driver}
EXE_DEFS="-DAETHER_PRECLAMP_INSTR_ENV_OFFICIAL=1 -DAETHER_REPLAY_LINK_REAL_GPU_MATCH=1 -DCOLMAP_CUDA_ENABLED=0 -DEIGEN_MPL2_ONLY -DGLOG_NO_ABBREVIATED_SEVERITIES -DGLOG_USE_GLOG_EXPORT -DGLOG_VERSION_MAJOR=0 -DGLOG_VERSION_MINOR=7 -DGLOMAP_CUDA_DISABLED -DFIXD_REAL_GPU_EXTRACT=1"
EXE_INC="-I$PW/include -I$S/official_pipeline/include -I$S/third_party/glomap_vendor/colmap-src -I$S/third_party/glomap_vendor/poselib-src -I$S/third_party/glomap_vendor/stubs -I$S/include -I/opt/homebrew/include -I/opt/homebrew/include/eigen3 -I$TP/glog-install/include -I$TP/ceres/include -I$TP/ceres-build-ios/include -I$TP/ceres/config -I$TP/eigen-install/include/eigen3"
cd $W/build
/usr/bin/c++ $EXE_DEFS $EXE_INC -O3 -DNDEBUG -std=gnu++17 -arch arm64 -fPIE -w -c $W/driver/fixd_replay_driver.cc -o fixd_replay_driver.o
/usr/bin/c++ -O3 -DNDEBUG -arch arm64 -Wl,-search_paths_first -Wl,-headerpad_max_install_names fixd_replay_driver.o coreobj/*.o \
  $GPUOBJ/sift_extract_dawn.o $GPUOBJ/sift_pyramid_dawn.o $GPUOBJ/dawn_kernel_harness.o $GPUOBJ/dsp_sift_gpu_c.o $GPUOBJ/canonical_feature_selector_v1.o \
  libcolmap_reuse_sep9host.a /Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/build-macos-dawn/third_party/dawn/src/dawn/native/libwebgpu_dawn.a \
  -framework Metal -framework Foundation -framework CoreGraphics -framework ImageIO -framework CoreFoundation -framework IOSurface -framework QuartzCore -framework Cocoa -framework IOKit \
  /opt/homebrew/lib/libceres.dylib /opt/homebrew/lib/libglog.dylib /opt/homebrew/lib/libjpeg.dylib -lsqlite3 -o $OUT
ls -la $OUT
