#!/usr/bin/env bash
# A4 的 Android 半边:构建 ORT(带 WebGPU EP)+ bench 原生可执行 + 推设备跑。
#
# ⚠️ 2026-08-18 写就时**手头无 Android 设备,本脚本未经运行验证**。
#    任何"跑通"的结论必须以真机输出为准。
#
# 为什么是原生可执行而不是 APK:bench 只需要 adb shell 跑一个二进制,
# 不需要 Activity/权限/签名。省掉整套 Android 工程,也不碰产品 app。
set -euo pipefail

: "${ANDROID_NDK_HOME:?请设 ANDROID_NDK_HOME(如 ~/Library/Android/sdk/ndk/27.x)}"
: "${ANDROID_SDK_ROOT:=$HOME/Library/Android/sdk}"
ORT_SRC="${ORT_SRC:-$HOME/Documents/progecttwo/.deps/onnxruntime}"
BUILD="${BUILD:-$HOME/Documents/progecttwo/.deps/ort_android}"
ABI="${ABI:-arm64-v8a}"
API="${API:-28}"          # WebGPU/Vulkan 需要较新的 API;28 是保守起点
DEV_DIR=/data/local/tmp/pwbench

echo "══ 1. 构建 ORT for Android(带 WebGPU EP)══"
# ⚠️ 与 iOS 不同,Android 不强制 Xcode 生成器,Ninja 可用。
# ⚠️ 若装了 Homebrew 的 onnx/protobuf,先 `brew unlink onnx protobuf abseil`,
#    否则 /opt/homebrew/include 会遮蔽 ORT 自带的 onnx(macOS 主机上踩过)。
python3 "$ORT_SRC/tools/ci_build/build.py" \
  --build_dir "$BUILD" --config Release --parallel \
  --skip_tests --skip_submodule_sync \
  --android --android_abi "$ABI" --android_api "$API" \
  --android_sdk_path "$ANDROID_SDK_ROOT" --android_ndk_path "$ANDROID_NDK_HOME" \
  --use_webgpu --build_shared_lib --cmake_generator Ninja \
  --cmake_extra_defines onnxruntime_BUILD_UNIT_TESTS=OFF

echo "══ 2. 编 bench ══"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$BUILD/pwbench"
"$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/darwin-x86_64/bin/clang++" \
  --target="aarch64-linux-android$API" \
  --sysroot="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/darwin-x86_64/sysroot" \
  -std=c++17 -O2 -fPIE -pie \
  -I"$ORT_SRC/include/onnxruntime/core/session" \
  "$HERE/bench_main.cc" \
  -L"$BUILD/Release" -lonnxruntime -llog \
  -o "$OUT"
echo "  ✅ $OUT"

echo "══ 3. 推设备 ══"
adb shell "mkdir -p $DEV_DIR"
adb push "$OUT" "$DEV_DIR/pwbench"
adb push "$BUILD/Release/libonnxruntime.so" "$DEV_DIR/"
adb push "${MODEL:?请设 MODEL=.../casdiffmvs_v5.onnx}" "$DEV_DIR/model.onnx"
adb push "${INPUTS:?请设 INPUTS=.../inputs8.bin}" "$DEV_DIR/inputs.bin"
adb shell "chmod +x $DEV_DIR/pwbench"

echo "══ 4. 跑(EP=1 即 WebGPU)══"
# ⚠️ 拔线安全:这是纯计算,不依赖持续连接;断了重连再看输出即可。
adb shell "cd $DEV_DIR && LD_LIBRARY_PATH=$DEV_DIR ./pwbench model.onnx inputs.bin 1"
echo
echo "══ 5. 对照:同一份图跑 CPU EP ══"
adb shell "cd $DEV_DIR && LD_LIBRARY_PATH=$DEV_DIR ./pwbench model.onnx inputs.bin 0"
