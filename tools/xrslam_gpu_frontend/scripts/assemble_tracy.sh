#!/bin/bash
set -uo pipefail
X=$HOME/Developer/xrslam-4beb1a9-thr; B=$X/build-gpufe-nothread-tracy
# [2026-09-16] 产物改放 ~/Developer:上一版写死了某个会话的 /tmp scratchpad,
# 那个目录被清掉后归档成员变 0、ABI 自证全 ✗,而下游 build 脚本的 cp 失败
# 却不报错 —— 会静默编出错引擎的包。
SP=$HOME/Developer/viobench-build/engine
mkdir -p "$SP"
OUT=$SP/libxrslam_gpufe_nothread_tracy.a
OBJS=()
while IFS= read -r line; do OBJS+=("$line"); done < <(find "$B/xrslam-interface/CMakeFiles" "$B/xrslam-localization/CMakeFiles" -name "*.cpp.o" | sort)
echo "散装目标文件 ${#OBJS[@]} 个"
xcrun libtool -static -o "$OUT" \
  "$B/xrslam/libxrslam-core.a" "$B/xrslam-extra/libxrslam-extra-opencv-image.a" \
  "$B/xrslam-extra/libxrslam-extra-yaml-config.a" "$B/_deps/depends-yaml-cpp-build/libyaml-cpp.a" \
  "${OBJS[@]}" 2>&1 | grep -v "has no symbols" | head -3
N=$(xcrun ar -t "$OUT" 2>/dev/null | grep -c "\.o$")
echo "归档成员 $N (gpufe 原版 57)  $(stat -f%z "$OUT" 2>/dev/null) bytes"
xcrun nm "$OUT" > "$SP/nothread_tracy_syms.txt" 2>/dev/null
for s in XRSLAMGetPropagatedPose XRSLAMGetInitCounters; do
  if grep -qE "T _$s" "$SP/nothread_tracy_syms.txt"; then echo "  ABI ✓ $s"; else echo "  ✗ 缺 $s"; fi
done
echo "=== 线程化真的关了吗(对照 gpufe) ==="
V=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64
for lib in "$OUT" "$V/libxrslam_gpufe_4beb1a9.a" "$V/libxrslam_generic_4beb1a9.a"; do
  printf "  %-34s THREADING字样 %s | GpuImage %s\n" "$(basename "$lib")" \
    "$(strings "$lib" 2>/dev/null | grep -c 'THREADING ENABLE')" \
    "$(xcrun nm -a "$lib" 2>/dev/null | grep -c 'GpuImage')"
done
