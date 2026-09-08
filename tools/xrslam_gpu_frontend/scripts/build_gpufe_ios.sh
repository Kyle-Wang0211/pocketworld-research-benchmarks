#!/bin/bash
# Rebuilt 2026-09-08 after ~/Developer/viobench-build was reclaimed: compiles the XRSLAM GPU front end
# (pw_gpu_frontend.cpp + Dawn harness) for iOS into libpw_gpu_frontend_ios.a.
# Flag recipe mirrors vendor/aether_ffi/build_gpu_extract_archive.sh (the device-proven TU/flag set).
set -euo pipefail
A="$HOME/Developer/Aether3D-cross/aether_cpp"; OUT="$HOME/Developer/viobench-build/gpufe"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
CXXFLAGS=(-target arm64-apple-ios16.0 -std=c++20 -stdlib=libc++ -O2 -w
  -DAETHER_FEATURE_SELECTION_ENV_OFFICIAL=1 -DAETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1
  -I"$A/official_pipeline/src" -I"$A/tools" -I"$A/include"
  -I"$A/third_party/dawn/include" -I"$A/build-ios-device-dawn/third_party/dawn/gen/include"
  # Dawn fingerprint the probe reports: revision = third_party/dawn HEAD, hash = the exact iOS archive this app links
  "-DAETHER_GPU_TIMESTAMP_DAWN_REVISION=\"$(cd "$A/third_party/dawn" && git rev-parse HEAD)\""
  "-DAETHER_GPU_TIMESTAMP_DAWN_ARTIFACT_SHA256=\"$(shasum -a256 "$A/build-ios-device-dawn/third_party/dawn/src/dawn/native/Debug-iphoneos/libwebgpu_dawn.a" | cut -d' ' -f1)\"")
mkdir -p "$OUT"; OBJS=()
for src in "$A/tools/dawn_kernel_harness.cpp" "$A/tools/pw_gpu_frontend.cpp"; do
  extra=""; [ "$(basename "$src")" = pw_gpu_frontend.cpp ] && extra="-ffp-contract=off"   # CLAHE weight tables must round like OpenCV
  echo "CXX $(basename "$src")"; xcrun -sdk iphoneos clang++ "${CXXFLAGS[@]}" $extra -c "$src" -o "$TMP/$(basename "${src%.*}").o"
  OBJS+=("$TMP/$(basename "${src%.*}").o")
done
rm -f "$OUT/libpw_gpu_frontend_ios.a"; xcrun -sdk iphoneos ar rcs "$OUT/libpw_gpu_frontend_ios.a" "${OBJS[@]}"
echo "OK $(shasum -a256 "$OUT/libpw_gpu_frontend_ios.a" | cut -c1-16)"
