#!/bin/bash
# Builds the macOS CLI shell + engine + vendored LOD library.
# Dawn: a SNAPSHOT of the macOS static lib from the shared Aether3D-cross tree is
# copied under build/ first (that tree is rebuilt by other sessions); its sha256
# is printed so a run can be tied to the exact lib.
set -eu
cd "$(dirname "$0")/.."
A=~/Developer/Aether3D-cross/aether_cpp
DEPS=build/mac_deps
mkdir -p $DEPS build/mac
if [ ! -f $DEPS/libwebgpu_dawn.a ]; then
  cp $A/build-macos-dawn/third_party/dawn/src/dawn/native/libwebgpu_dawn.a $DEPS/
  cp -R $A/third_party/dawn/include $DEPS/dawn_include
  cp -R $A/build-macos-dawn/third_party/dawn/gen/include $DEPS/dawn_gen_include
fi
shasum -a 256 $DEPS/libwebgpu_dawn.a
V=third_party/aether_pointcloud_lod
STRICT="-std=c++17 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror -fno-exceptions -fno-rtti"
for s in octree select stream; do
  clang++ $STRICT -I$V/include -I$V/third_party -c $V/src/$s.cpp -o build/mac/lod_$s.o
done
clang++ $STRICT -I$V/include -I$DEPS/dawn_include -I$DEPS/dawn_gen_include -ISources/lod \
  -c Sources/lod/pw_lod_bench.cpp -o build/mac/pw_lod_bench.o
clang++ $STRICT -ISources/lod -c mac/main_lod_mac.cpp -o build/mac/main.o
clang++ -o build/mac/pwlod_mac build/mac/main.o build/mac/pw_lod_bench.o build/mac/lod_*.o \
  $DEPS/libwebgpu_dawn.a -lz -lc++ \
  -framework CoreFoundation -framework Foundation -framework QuartzCore -framework Cocoa \
  -framework IOKit -framework Metal -framework CoreVideo -framework IOSurface -framework CoreML
echo "built build/mac/pwlod_mac"
