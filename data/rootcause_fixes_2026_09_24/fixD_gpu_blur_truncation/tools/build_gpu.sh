#!/bin/bash
# build_gpu.sh [src_root] [objdir] [out] — host (macOS, Dawn/Metal) build of the shipped GPU DSP-SIFT carrier
# sources (pwofficial_gpu_extract target, aether_cpp/CMakeLists.txt @568f53d3 "P3a1 OFFICIAL GPU CARRIER"),
# WGSL read at runtime from the same tree (AETHER_WGSL_DIR). Dawn = read-only prebuilt macOS bundle.
set -euo pipefail
S=${1:-/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD/gpu568/aether_cpp}; O=${2:-/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD/build/gpuobj}; OUT=${3:-/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD/build/gpu_extract}
D=/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp
mkdir -p $O
DEFS="-DAETHER_FEATURE_SELECTION_ENV_OFFICIAL=1 -DAETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1 -DAETHER_GPU_TIMESTAMP_DAWN_REVISION=\"12ee391c7411285895f4289a3d889a182c093014\" -DAETHER_GPU_TIMESTAMP_DAWN_ARTIFACT_SHA256=\"host\" -DAETHER_WGSL_DIR=\"$S/shaders/wgsl\""
INC="-I$S/tools -I$S/include -I$S/official_pipeline/src -I$D/third_party/dawn/include -I$D/build-macos-dawn/third_party/dawn/gen/include"
FL="-O2 -std=gnu++20 -arch arm64 -w"
for src in tools/sift_extract_dawn.cc tools/sift_pyramid_dawn.cc tools/dawn_kernel_harness.cpp third_party/glomap_vendor/bench/dsp_sift_gpu_c.cc src/sfm/canonical_feature_selector_v1.cc official_pipeline/src/official_preclamp_instr_v1.cc src/crypto/sha256.cpp; do
  b=$(basename $src); /usr/bin/c++ $DEFS $INC $FL -c $S/$src -o $O/${b%.*}.o &
done
/usr/bin/c++ -O2 -std=gnu++17 -arch arm64 -c /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD/tools/gpu_extract.cc -o $O/gpu_extract_main.o &
wait
/usr/bin/c++ -O2 -arch arm64 $O/*.o $D/build-macos-dawn/third_party/dawn/src/dawn/native/libwebgpu_dawn.a   -framework CoreFoundation -framework Foundation -framework IOSurface -framework QuartzCore -framework Cocoa -framework IOKit -framework Metal -o $OUT
ls -la $OUT
