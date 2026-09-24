#!/bin/zsh
# usage: build.sh <runner_include_dir> <stub.c> <out>
set -e
SM=${0:A:h}; R_INC=$1; STUB=$2; OUT=$3
R=~/Developer/pw-lod-viewer/ios/Runner
DEPS=~/Developer/pw_splat_ab_bench/build/mac_deps
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
FW=/opt/homebrew/share/flutter/bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64
DAWN=~/Developer/Aether3D-cross/aether_cpp/build-ios-device-dawn/third_party/dawn/src/dawn/native/Release-iphoneos/libwebgpu_dawn.a
V=$R_INC/../../vendor/aether_lod/include
xcrun --sdk iphoneos clang -arch arm64 -miphoneos-version-min=15.0 -Wall -Wextra -Werror -I$V -I$DEPS/dawn_gen_include -I$DEPS/dawn_include -c $STUB -o $SM/stub_$OUT.o
xcrun --sdk iphoneos clang -arch arm64 -miphoneos-version-min=15.0 -fobjc-arc -Wall -Wextra -Werror -I$DEPS/dawn_gen_include -I$DEPS/dawn_include -c $R_INC/PwLodSurface.m -o $SM/surf_$OUT.o
xcrun --sdk iphoneos swiftc -target arm64-apple-ios15.0 -sdk $SDK -swift-version 5 -warnings-as-errors \
  -import-objc-header $SM/Smoke-Bridging.h -Xcc -I$SM -Xcc -F$FW -Xcc -I$R_INC -Xcc -I$DEPS/dawn_gen_include -Xcc -I$DEPS/dawn_include -F $FW \
  $R/PwLodTexture.swift $R/PwLodTexturePlugin.swift $R/PwLodProbe.swift $SM/main.swift \
  $SM/surf_$OUT.o $SM/stub_$OUT.o $SM/gpr.o $DAWN -lc++ -framework Flutter -framework Metal -framework QuartzCore \
  -framework IOSurface -framework CoreVideo -framework Foundation -framework UIKit -framework IOKit \
  -Xlinker -rpath -Xlinker @executable_path/Frameworks -o $SM/$OUT
