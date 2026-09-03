#!/usr/bin/env bash
# fair_match_build.sh — builds the H2 fair matcher harness (extractor +
# native Metal arm + portable Dawn/WGSL arm) into $1 (default /private/tmp
# workdir). Records source and binary SHA-256 into $OUT/build_identity.txt.
set -euo pipefail

tools_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$tools_dir/../../../.." && pwd)"
OUT="${1:-/private/tmp/aether-host-speed-h2-matcher/build}"
mkdir -p "$OUT"

DAWN_INC="$repo_dir/aether_cpp/third_party/dawn/include"
DAWN_GEN="$repo_dir/aether_cpp/build/third_party/dawn/gen/include"
DAWN_LIB="$repo_dir/aether_cpp/build/third_party/dawn/src/dawn/native/libwebgpu_dawn.a"
MATCHER="$repo_dir/aether_cpp/official_pipeline/src/official_gpu_match.mm"
INC="$repo_dir/aether_cpp/include"

xcrun clang++ -O2 -std=c++20 -arch arm64 \
  "$tools_dir/fair_match_extract_fixture.cc" -lsqlite3 \
  -o "$OUT/fair_match_extract_fixture"

xcrun clang++ -O2 -std=c++20 -arch arm64 -I"$INC" \
  "$tools_dir/fair_match_native_arm.mm" "$MATCHER" \
  -framework Metal -framework Foundation \
  -o "$OUT/fair_match_native_arm"

xcrun clang++ -O2 -std=c++20 -arch arm64 \
  -I"$DAWN_INC" -I"$DAWN_GEN" \
  "$tools_dir/fair_match_portable_arm.cc" "$DAWN_LIB" \
  -framework CoreFoundation -framework Foundation -framework IOSurface \
  -framework QuartzCore -framework Cocoa -framework IOKit -framework Metal \
  -o "$OUT/fair_match_portable_arm"

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "clang: $(xcrun clang++ --version | head -1)"
  echo "== sources =="
  shasum -a 256 \
    "$tools_dir/fair_match_common.h" \
    "$tools_dir/fair_match_extract_fixture.cc" \
    "$tools_dir/fair_match_native_arm.mm" \
    "$tools_dir/fair_match_portable_arm.cc" \
    "$MATCHER"
  echo "== dawn =="
  shasum -a 256 "$DAWN_LIB" | awk '{print $1"  libwebgpu_dawn.a"}'
  echo "== binaries =="
  shasum -a 256 "$OUT/fair_match_extract_fixture" \
    "$OUT/fair_match_native_arm" "$OUT/fair_match_portable_arm"
} > "$OUT/build_identity.txt"
cat "$OUT/build_identity.txt"
echo "BUILD_OK $OUT"
