#!/bin/bash
set -uo pipefail
T=$HOME/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench
V=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64
BD=$HOME/Developer/viobench-build
A=$HOME/Developer/Aether3D-cross/aether_cpp
SP=$HOME/Developer/viobench-build/engine
GPUFE=$BD/gpufe/libpw_gpu_frontend_ios.a
# [2026-09-16] Dawn 档位。Debug 版带完整 WebGPU 校验(库内 "Validation" 字样 17070 处,
# Release 只有 76),而我们每帧都提交 GPU 工作 —— 台架实测空提交 6.0-13.2 ms,
# 原生量级不该是这个数。PW_DAWN_FLAVOR=Debug 可切回对照。
DAWN_FLAVOR=${PW_DAWN_FLAVOR:-Release}
DAWN=$A/build-ios-device-dawn/third_party/dawn/src/dawn/native/$DAWN_FLAVOR-iphoneos/libwebgpu_dawn.a
[ -s "$DAWN" ] || { echo "✗ 缺 $DAWN"; exit 1; }
echo "Dawn 档位: $DAWN_FLAVOR ($(stat -f%z "$DAWN") bytes)"
# 缺了就停:cp 静默失败会让 vendor 里留着 generic 档,编出的包引擎是错的,
# 而四道字节自证照样全绿(它们只证「装的是我想装的字节」)。
[ -s "$SP/libxrslam_gpufe_nothread_tracy.a" ] || { echo "✗ 缺 $SP/libxrslam_gpufe_nothread_tracy.a,拒绝构建"; exit 1; }
cp "$SP/libxrslam_gpufe_nothread_tracy.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a" || { echo "✗ cp 失败"; exit 1; }
DD="$BD/bench-dd-tracy"; rm -rf "$DD"
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
