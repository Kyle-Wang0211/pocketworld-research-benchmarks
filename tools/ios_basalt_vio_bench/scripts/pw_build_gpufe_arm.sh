#!/bin/bash
# gpufe arm: libxrslam_gpufe_4beb1a9.a (XRSLAM_GPU_FRONTEND=ON, threading+gate as thrbp) + libpw_gpu_frontend_ios.a + Dawn.
set -eo pipefail
T=$(cd "$(dirname "$0")/.." && pwd); V=~/Developer/pocketworld/vendor/xrslam/libs/ios-arm64; BD=~/Developer/viobench-build; A=~/Developer/Aether3D-cross/aether_cpp
GPUFE=$BD/gpufe/libpw_gpu_frontend_ios.a; DAWN=$A/build-ios-device-dawn/third_party/dawn/src/dawn/native/Debug-iphoneos/libwebgpu_dawn.a
[ -f "$V/libxrslam_gpufe_4beb1a9.a" ] && [ -f "$GPUFE" ] && [ -f "$DAWN" ] || { echo "missing arm inputs"; exit 1; }
cp "$V/libxrslam_gpufe_4beb1a9.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"
DD="$BD/bench-dd-gpufe"; rm -rf "$DD"
EXTRA="-force_load $GPUFE $DAWN -framework Metal -framework IOSurface -framework QuartzCore -framework CoreVideo"
(cd "$T" && LANG=en_US.UTF-8 xcodebuild -project VIOReplacementBench.xcodeproj -scheme VIOReplacementBench -configuration Release -destination 'generic/platform=iOS' -derivedDataPath "$DD" -allowProvisioningUpdates "PW_XRSLAM_EXTRA_LDFLAGS=$EXTRA" build 2>&1 | grep -E "error:|BUILD (SUCCEEDED|FAILED)" | tail -3)
APP="$DD/Build/Products/Release-iphoneos/VIOReplacementBench.app"
shasum -a 256 "$V/libxrslam_gpufe_4beb1a9.a" | cut -d' ' -f1 > "$DD/ENGINE_A_SHA256"; shasum -a 256 "$GPUFE" | cut -d' ' -f1 > "$DD/GPUFE_A_SHA256"
echo "  engine sha16 $(shasum -a 256 "$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" | cut -c1-16)  xrslam.a $(cut -c1-16 "$DD/ENGINE_A_SHA256")  gpufe.a $(cut -c1-16 "$DD/GPUFE_A_SHA256")  engine size $(du -h "$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" | cut -f1)"
xcrun nm "$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" 2>/dev/null | grep -c "GpuImage" || true
cp "$V/libxrslam_generic_4beb1a9.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"; (cd "$T" && sh scripts/verify_vendor.sh >/dev/null 2>&1 && echo "vendor 已还原,verify 绿")
