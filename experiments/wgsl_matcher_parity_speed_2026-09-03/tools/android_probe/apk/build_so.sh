#!/bin/bash
# 用当前产品 TU 重编探针 .so(NDK clang,链接为 Android arm64 单独编的 Dawn/Vulkan)。
set -euo pipefail
P=~/Developer/pw_android_probe; A=~/Developer/Aether3D-cross/aether_cpp; B=~/Developer/dawn-android-arm64
S=${PW_TU_DIR:-$HOME/Developer/pw-head-0827/vendor/official_sfm/src}
NDK=/opt/homebrew/share/android-ndk/toolchains/llvm/prebuilt/darwin-x86_64/bin
OUT=$P/apk/lib/arm64-v8a/libpwprobe.so; mkdir -p "$(dirname $OUT)"
TUSHA=$(shasum -a 256 $S/pwofficial_gpu_match_dawn.cc | cut -c1-12); echo "$TUSHA" > $P/apk/out_build_id.txt
$NDK/clang++ --target=aarch64-linux-android26 -O3 -std=c++17 -fno-rtti -fPIC -shared -DPW_PROBE_BUILD_ID="\"$TUSHA\"" \
  -I$A/third_party/dawn/include -I$B/gen/include -I$HOME/Developer/pw-head-0827/vendor/official_sfm/include \
  $P/apk/jni/pwprobe_jni.cc $S/pwofficial_gpu_match_dawn.cc \
  $B/src/dawn/native/libwebgpu_dawn.a -llog -landroid -static-libstdc++ -o $OUT
$NDK/llvm-strip $OUT
shasum -a 256 $S/pwofficial_gpu_match_dawn.cc | cut -c1-12 | sed 's/^/TU sha: /'
ls -la $OUT | awk '{print "so:", $5, "bytes"}'
