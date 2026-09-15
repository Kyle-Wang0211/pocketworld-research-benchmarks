#!/bin/bash
set -uo pipefail
T=$HOME/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench
V=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64
BD=$HOME/Developer/viobench-build
A=$HOME/Developer/Aether3D-cross/aether_cpp
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/a4f1b282-3935-42e4-b01e-3c7d57f1276e/scratchpad
GPUFE=$BD/gpufe/libpw_gpu_frontend_ios.a
DAWN=$A/build-ios-device-dawn/third_party/dawn/src/dawn/native/Debug-iphoneos/libwebgpu_dawn.a
cp "$SP/libxrslam_gpufe_nothread.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"
DD="$BD/bench-dd-nothread"; rm -rf "$DD"
EXTRA="-force_load $GPUFE $DAWN -framework Metal -framework IOSurface -framework QuartzCore -framework CoreVideo"
cd "$T" && LANG=en_US.UTF-8 xcodebuild -project VIOReplacementBench.xcodeproj -scheme VIOReplacementBench \
  -configuration Release -destination 'generic/platform=iOS' -derivedDataPath "$DD" -allowProvisioningUpdates \
  "PW_XRSLAM_EXTRA_LDFLAGS=$EXTRA" build 2>&1 | grep -E "error:|BUILD (SUCCEEDED|FAILED)" | tail -3
APP="$DD/Build/Products/Release-iphoneos/VIOReplacementBench.app"
if [ -d "$APP" ]; then
  E="$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine"
  echo "engine sha16 $(shasum -a 256 "$E" | cut -c1-16)  大小 $(stat -f%z "$E")"
  echo "探针: @compute $(strings "$E" | grep -c '@compute')  THREADING $(strings "$E" | grep -c 'THREADING ENABLE')  GPU_WAIT_MS $(strings "$E" | grep -c 'OFFICIAL_AETHER_GPU_WAIT_MS')"
fi
# 还原 vendor
cp "$V/libxrslam_generic_4beb1a9.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"
echo "vendor 已还原: $(shasum -a 256 "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a" | cut -c1-16)"
