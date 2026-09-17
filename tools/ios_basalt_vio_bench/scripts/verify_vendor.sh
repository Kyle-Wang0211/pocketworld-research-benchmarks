#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BENCH_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)
VENDOR_ROOT="${BENCH_ROOT}/Vendor"
BASALT_ROOT="${VENDOR_ROOT}/basalt"
HEADERS_ROOT="${VENDOR_ROOT}/basalt-headers"
VCPKG_ROOT="${BASALT_ROOT}/thirdparty/vcpkg"
ALLOWLIST="${VENDOR_ROOT}/basalt_vio_source_allowlist.tsv"
XR_VENDOR_ROOT=${PW_XRSLAM_VENDOR_ROOT:-"${VENDOR_ROOT}/xrslam"}
XR_BACKEND_ROOT=${PW_XRSLAM_BACKEND_ROOT:-"${BENCH_ROOT}/XRSLAMBackend"}
XR_RECEIPT="${XR_VENDOR_ROOT}/lib/libxrslam_generic_4beb1a9.receipt.json"
XR_PATCH=${PW_XRSLAM_PATCH:-"${VENDOR_ROOT}/patches/xrslam_destroy_lifecycle.patch"}
XR_PATCH_MASK=${PW_XRSLAM_MASK_PATCH:-"${VENDOR_ROOT}/patches/xrslam_zero_inlier_mask.patch"}
XR_OPENCV_HEADERS="${XR_VENDOR_ROOT}/opencv-4.0.1-headers"

BASALT_COMMIT=0f3b2b52c807f70ff4e2973ce253c73329eea7bc
HEADERS_COMMIT=aa441ba3e51050c47ba1902537792a2e4db7e43d
VCPKG_COMMIT=1e199d32ad53aab1defda61ce41c380302e3f95c
REGISTRY_BASELINE=05442024c3fda64320bd25d2251cc9807b84fb6f

fail() {
  printf 'vendor verification failed: %s\n' "$*" >&2
  exit 1
}

require_equal() {
  actual=$1
  expected=$2
  label=$3
  [ "$actual" = "$expected" ] || fail "$label: expected $expected, got $actual"
}

require_sha256() {
  file=$1
  expected=$2
  [ -f "$file" ] || fail "missing file: $file"
  actual=$(shasum -a 256 "$file" | awk '{print $1}')
  require_equal "$actual" "$expected" "sha256 $file"
}

verify_repo() {
  repo=$1
  expected_commit=$2
  expected_url=$3
  [ -e "${repo}/.git" ] || fail "missing Git checkout: $repo"
  require_equal "$(git -C "$repo" rev-parse HEAD)" "$expected_commit" "commit $repo"
  require_equal "$(git -C "$repo" remote get-url origin)" "$expected_url" "origin $repo"
  git -C "$repo" diff --quiet --ignore-submodules=none -- || fail "working tree differs: $repo"
  git -C "$repo" diff --cached --quiet --ignore-submodules=none -- || fail "index differs: $repo"
}

verify_repo "$BASALT_ROOT" "$BASALT_COMMIT" \
  "https://gitlab.com/VladyslavUsenko/basalt.git"
verify_repo "$HEADERS_ROOT" "$HEADERS_COMMIT" \
  "https://gitlab.com/VladyslavUsenko/basalt-headers.git"
verify_repo "$VCPKG_ROOT" "$VCPKG_COMMIT" \
  "https://github.com/microsoft/vcpkg.git"

gitlink=$(git -C "$BASALT_ROOT" ls-tree HEAD thirdparty/vcpkg | awk '{print $3}')
require_equal "$gitlink" "$VCPKG_COMMIT" "Basalt vcpkg gitlink"
git -C "$VCPKG_ROOT" cat-file -e "${REGISTRY_BASELINE}^{commit}" 2>/dev/null || \
  fail "registry baseline object is not fetched: $REGISTRY_BASELINE"

baseline=$(sed -n 's/.*"baseline"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' \
  "${BASALT_ROOT}/vcpkg-configuration.json")
require_equal "$baseline" "$REGISTRY_BASELINE" "upstream registry baseline"
bench_baseline=$(sed -n 's/.*"baseline"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' \
  "${BENCH_ROOT}/cmake/vcpkg/vcpkg-configuration.json")
require_equal "$bench_baseline" "$REGISTRY_BASELINE" "bench registry baseline"

headers_ref=$(sed -n 's/^[[:space:]]*REF[[:space:]]*\([0-9a-f]*\).*/\1/p' \
  "${BASALT_ROOT}/vcpkg/ports/basalt-headers/portfile.cmake")
require_equal "$headers_ref" "$HEADERS_COMMIT" "basalt-headers overlay ref"
opengv_ref=$(sed -n 's/^[[:space:]]*REF[[:space:]]*\([0-9a-f]*\).*/\1/p' \
  "${BASALT_ROOT}/vcpkg/ports/opengv/portfile.cmake")
require_equal "$opengv_ref" 91f4b19c73450833a40e463ad3648aae80b3a7f3 "OpenGV overlay ref"

require_sha256 "${BASALT_ROOT}/LICENSE" 8abbeeb535841bbf306a006b54b5829974156abd98a68f6398558db43a51dd0c
require_sha256 "${HEADERS_ROOT}/LICENSE" 8abbeeb535841bbf306a006b54b5829974156abd98a68f6398558db43a51dd0c
require_sha256 "${VCPKG_ROOT}/LICENSE.txt" 1ee376fc340e0aa6ad6a3581c94126e741468705096ac92263048a21daa86460
require_sha256 "${BASALT_ROOT}/data/euroc_config.json" 82937bd6493e592ef89572d31260c10f7437b4fb3ff1fda179375713966e34fa
require_sha256 "${BASALT_ROOT}/vcpkg.json" 3616ac19a2d400b2eaf1a4490d0176dd4bda86c17740e4fb37f7bac2d5f8f0a1
require_sha256 "${BASALT_ROOT}/vcpkg-configuration.json" 28aeb591c23215efc5cddd5cb9234bf862489698f9ca0c21591a08bdf9293ae1
require_sha256 "${BASALT_ROOT}/vcpkg/ports/opengv/portfile.cmake" 77141e9f3c078a0372a4c59cb0a7b6bd4ba2c6d781a0b85cd079af219616b9f6
require_sha256 "${BASALT_ROOT}/vcpkg/ports/basalt-headers/portfile.cmake" 565a380bcb0969796e7167547c5b9de273d3866ba912ef8ed9069e4ab925f37d
require_sha256 "${BENCH_ROOT}/cmake/vcpkg/vcpkg.json" ed17cd18697454aeb0b1a96e374f8b149327b942e23cd53b5c39cd8162d4fc08
require_sha256 "${BENCH_ROOT}/cmake/vcpkg/vcpkg-configuration.json" d13de34ee24705050b64986b4ca495492bc3dcd1d1b0ac1ed0e6de30eb2e3c97
require_sha256 "${BENCH_ROOT}/cmake/triplets/arm64-ios17-release.cmake" 369748bcee33236478f9f1f53392bff6d7c3e4a6c276446ef441ec20064bee66

[ -f "$ALLOWLIST" ] || fail "missing source allowlist"
source_count=0
seen_paths=''
while IFS="	" read -r expected_hash relative_path; do
  case "$expected_hash" in
    ''|'#'*) continue ;;
  esac
  printf '%s' "$expected_hash" | grep -Eq '^[0-9a-f]{64}$' || \
    fail "malformed sha256 in allowlist: $expected_hash"
  printf '%s' "$relative_path" | grep -Eq \
    '^src/(linearization|optical_flow|utils|vi_estimator)/[^/]+\.cpp$' || \
    fail "source outside frozen VIO slice: $relative_path"
  case "\n${seen_paths}\n" in
    *"\n${relative_path}\n"*) fail "duplicate source: $relative_path" ;;
  esac
  seen_paths="${seen_paths}
${relative_path}"
  require_sha256 "${BASALT_ROOT}/${relative_path}" "$expected_hash"
  source_count=$((source_count + 1))
done < "$ALLOWLIST"
require_equal "$source_count" 16 "frozen VIO source count"

if grep -Eiq 'pangolin|rosbag|realsense|mapper|sqrt_keypoint_vo|src/vio\.cpp|src/opt_flow\.cpp' "$ALLOWLIST"; then
  fail "desktop, mapping, or VO source entered the VIO allowlist"
fi
if grep -Eiq 'pangolin|rosbag|realsense|boost|cli11|gtest' \
    "${BENCH_ROOT}/cmake/vcpkg/vcpkg.json"; then
  fail "desktop-only dependency entered the iOS VIO manifest"
fi

require_sha256 "${XR_VENDOR_ROOT}/lib/libxrslam_generic_4beb1a9.a" \
  fdc75c99358014d9485bea36667547825465a85562847548d02a582da38c8011
require_sha256 "${XR_VENDOR_ROOT}/lib/libceres_official_1_14.a" \
  0e3769d937df9610042636960c56411c3a6aa37c00b42d0eae8aa279503e4bb6
require_sha256 "${XR_VENDOR_ROOT}/lib/libopencv_generic_4_0_1.a" \
  2dac46bd0a07a80fa8f8e6edc736b3fb0b679e91c120b2a1aab789b801dce56d
require_sha256 "$XR_RECEIPT" \
  1b9d065939e718ae2a8c53b84dbb4d82fc3466448b7ef180ff535cfd4cf67fdf
require_sha256 "$XR_PATCH" \
  13592cb486f159217fa5ecf9ef2f9863be78cf599d42fb1757e34bd7d4bbb220
require_sha256 "$XR_PATCH_MASK" \
  62b12204c647e445e88917859de6b29452df0e6cc65b447e7ea86005f98d1794
require_sha256 "${XR_VENDOR_ROOT}/include/XRSLAM.h" \
  505556e153861d07b820bb50293186fcfb5546f57385cd070320d119a31e62e7
require_sha256 "${XR_BACKEND_ROOT}/Native/Frozen/XRSLAM.h" \
  505556e153861d07b820bb50293186fcfb5546f57385cd070320d119a31e62e7
require_sha256 "${XR_BACKEND_ROOT}/Config/xrslam_ios_vio.yaml" \
  2de486a404e32bfbcee461247dc284b1b9cef8a6bb0d37b296ed12d33038c6e2
require_sha256 "${XR_BACKEND_ROOT}/Config/xrslam_iphone_14_pro.yaml" \
  0d8fafcdafd7ab4f49e8b555dbd8b74a4fbb07324224a38afb8087003373c157
require_sha256 "${XR_BACKEND_ROOT}/Config/xrslam_euroc_vio.yaml" \
  d80820dfdc316ad504a8bf7186d785ea807397d17069d50658bfa0f46d391502
require_sha256 "${XR_BACKEND_ROOT}/Config/xrslam_euroc_sensor.yaml" \
  6ddfda8e53f6dd3c98a43b28e7b7b945133c651b298a4fc150acdaa635d69748
require_sha256 "${XR_OPENCV_HEADERS}/MANIFEST.sha256" \
  454d456757fb92eb7cb61442b283f834b2f9f696e730a7adeeb0133c48e375ad
(cd "$XR_OPENCV_HEADERS" && shasum -a 256 -c MANIFEST.sha256 >/dev/null) || \
  fail "XRSLAM OpenCV 4.0.1 header manifest differs"

/usr/bin/python3 - "${XR_OPENCV_HEADERS}/PROVENANCE.json" <<'PY' || \
  fail "XRSLAM OpenCV 4.0.1 header provenance differs"
import json
import sys

receipt = json.load(open(sys.argv[1], "r", encoding="utf-8"))
expected = {
    "project": "OpenCV",
    "canonical_repository": "https://github.com/opencv/opencv.git",
    "revision": "c9ad5779f2803dcc91a9938142209128d30b22d1",
    "version": "4.0.1",
    "source_archive_sha256": "4fcf6fd9d7bb996e9a9cf05ece1f10041873bf3291b038559a5464d48af5b5cf",
    "header_manifest_sha256": "454d456757fb92eb7cb61442b283f834b2f9f696e730a7adeeb0133c48e375ad",
}
for key, value in expected.items():
    if receipt.get(key) != value:
        raise SystemExit(f"OpenCV header provenance {key} differs")
PY

cmp -s "${XR_VENDOR_ROOT}/include/XRSLAM.h" \
  "${XR_BACKEND_ROOT}/Native/Frozen/XRSLAM.h" || \
  fail "XRSLAM public and frozen ABI headers differ"

/usr/bin/python3 - "$XR_RECEIPT" <<'PY' || fail "XRSLAM receipt semantics differ"
import json
import sys

receipt = json.load(open(sys.argv[1], "r", encoding="utf-8"))
expected = {
    "artifact": "libxrslam_generic_4beb1a9.a",
    "artifact_sha256": "fdc75c99358014d9485bea36667547825465a85562847548d02a582da38c8011",
    "upstream_revision": "4beb1a942f33da9afbfae2d70e2c641cfc2bb675",
    "xrslam_ios": False,
    "threading": False,
    "lifecycle_patch": "../../patches/xrslam_destroy_lifecycle.patch",
    "lifecycle_patch_sha256": "13592cb486f159217fa5ecf9ef2f9863be78cf599d42fb1757e34bd7d4bbb220",
    "zero_inlier_mask_patch": "../../patches/xrslam_zero_inlier_mask.patch",
    "zero_inlier_mask_patch_sha256": "62b12204c647e445e88917859de6b29452df0e6cc65b447e7ea86005f98d1794",
    "algorithm_change": True,
}
for key, value in expected.items():
    if receipt.get(key) != value:
        raise SystemExit(f"receipt {key}: expected {value!r}, got {receipt.get(key)!r}")
required_abi = {
    "XRSLAMCreate", "XRSLAMDestroy", "XRSLAMGetResult",
    "XRSLAMPushSensorData", "XRSLAMRunOneFrame",
}
if set(receipt.get("exported_abi", [])) != required_abi:
    raise SystemExit("receipt exported_abi differs")
PY

for archive in \
  "${XR_VENDOR_ROOT}/lib/libxrslam_generic_4beb1a9.a" \
  "${XR_VENDOR_ROOT}/lib/libceres_official_1_14.a" \
  "${XR_VENDOR_ROOT}/lib/libopencv_generic_4_0_1.a"; do
  xcrun lipo -info "$archive" | grep -q 'architecture: arm64' || \
    fail "XR dependency is not arm64: $archive"
done

xr_symbols=$(/usr/bin/nm -gU "${XR_VENDOR_ROOT}/lib/libxrslam_generic_4beb1a9.a")
for symbol in XRSLAMCreate XRSLAMDestroy XRSLAMGetResult XRSLAMPushSensorData XRSLAMRunOneFrame; do
  printf '%s\n' "$xr_symbols" | grep -q " T _${symbol}$" || \
    fail "missing XRSLAM ABI symbol: $symbol"
done

printf 'vendor verification passed\n'
printf '  Basalt:         %s\n' "$BASALT_COMMIT"
printf '  Basalt headers: %s\n' "$HEADERS_COMMIT"
printf '  vcpkg:          %s\n' "$VCPKG_COMMIT"
printf '  registry:       %s\n' "$REGISTRY_BASELINE"
printf '  VIO sources:    %s (all hashes matched)\n' "$source_count"
printf '  XRSLAM:         %s (archive, receipt, patch, ABI, configs matched)\n' \
  4beb1a942f33da9afbfae2d70e2c641cfc2bb675
