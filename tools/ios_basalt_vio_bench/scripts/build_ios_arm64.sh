#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BENCH_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)
VCPKG_ROOT="${BENCH_ROOT}/Vendor/basalt/thirdparty/vcpkg"
MANIFEST_ROOT="${BENCH_ROOT}/cmake/vcpkg"
TRIPLETS_ROOT="${BENCH_ROOT}/cmake/triplets"
BUILD_ROOT=${BASALT_VIO_BUILD_ROOT:-"${BENCH_ROOT}/Vendor/_build/ios-arm64-release"}
INSTALLED_ROOT=${BASALT_VIO_INSTALLED_ROOT:-"${BENCH_ROOT}/Vendor/_vcpkg_installed"}
DEPLOYMENT_TARGET=17.0

"${SCRIPT_DIR}/verify_vendor.sh"

if [ ! -x "${VCPKG_ROOT}/vcpkg" ]; then
  "${VCPKG_ROOT}/bootstrap-vcpkg.sh" -disableMetrics
fi

# `cmake --fresh` removes its cache but not CPack files emitted by an older
# configuration. Remove only those two generated files so stale packaging
# targets cannot survive into the VIO-only graph.
cmake -E rm -f "${BUILD_ROOT}/CPackConfig.cmake" "${BUILD_ROOT}/CPackSourceConfig.cmake"

cmake --fresh -S "${BENCH_ROOT}/cmake" -B "$BUILD_ROOT" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" \
  -DVCPKG_CHAINLOAD_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/toolchains/ios.cmake" \
  -DVCPKG_TARGET_TRIPLET=arm64-ios17-release \
  -DVCPKG_TARGET_ARCHITECTURE=arm64 \
  -DVCPKG_OVERLAY_TRIPLETS="$TRIPLETS_ROOT" \
  -DVCPKG_MANIFEST_DIR="$MANIFEST_ROOT" \
  -DVCPKG_INSTALLED_DIR="$INSTALLED_ROOT" \
  -DVCPKG_INSTALL_OPTIONS=--clean-after-build \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET"

cmake --build "$BUILD_ROOT" --target basalt_vio_core_link_probe --parallel

ARCHIVE="${BUILD_ROOT}/libbasalt_vio_core.a"
LINK_PROBE="${BUILD_ROOT}/basalt_vio_core_link_probe.app/basalt_vio_core_link_probe"
[ -f "$ARCHIVE" ] || {
  printf 'missing expected archive: %s\n' "$ARCHIVE" >&2
  exit 1
}
[ -f "$LINK_PROBE" ] || {
  printf 'missing expected link probe: %s\n' "$LINK_PROBE" >&2
  exit 1
}
lipo "$ARCHIVE" -verify_arch arm64
lipo "$LINK_PROBE" -verify_arch arm64
otool -l "$LINK_PROBE" | grep -A5 LC_BUILD_VERSION | grep -q 'platform 2'
otool -l "$LINK_PROBE" | grep -A5 LC_BUILD_VERSION | grep -q 'minos 17.0'

for dependency_archive in \
  libtbb.a \
  libopencv_core4.a \
  libopencv_imgproc4.a \
  libopencv_features2d4.a \
  libopencv_calib3d4.a \
  libopengv.a \
  libfmt.a \
  libz.a; do
  dependency_path="${INSTALLED_ROOT}/arm64-ios17-release/lib/${dependency_archive}"
  [ -f "$dependency_path" ] || {
    printf 'missing dependency archive: %s\n' "$dependency_path" >&2
    exit 1
  }
  deployment_versions=$(otool -l "$dependency_path" | \
    awk '/^[[:space:]]+minos /{print $2}' | sort -u)
  [ "$deployment_versions" = "17.0" ] || {
    printf 'unexpected deployment target in %s: %s\n' \
      "$dependency_archive" "$deployment_versions" >&2
    exit 1
  }
done

targets=$(cmake --build "$BUILD_ROOT" --target help)
if printf '%s\n' "$targets" | grep -Eiq \
    'pangolin|rosbag|realsense|mapper|calibrat|basalt_vio_sim|basalt_vio$|basalt_opt_flow'; then
  printf 'non-VIO target entered the iOS build graph\n' >&2
  exit 1
fi

printf 'iOS arm64 VIO-only archive built: %s\n' "$ARCHIVE"
lipo -info "$ARCHIVE"
printf 'full-closure iOS link probe built: %s\n' "$LINK_PROBE"
lipo -info "$LINK_PROBE"
