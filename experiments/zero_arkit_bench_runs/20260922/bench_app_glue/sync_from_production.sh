#!/usr/bin/env bash
# bench 里的 vio 代码是生产的**镜像**,不是分叉。真源在 pocketworld。
# 改动一律改生产,然后跑这个同步过来。跑完会自证逐字节一致。
set -euo pipefail
P=~/Developer/pocketworld; B="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 2026-09-18: 加上 ffi/ —— engine_pose_poller.dart 要 XrslamBindings 与 xrslamOk,
# 缺了这一层台架直接 6 个 undefined。镜像范围要跟着依赖走,不能只镜像"我改过的目录"。
mkdir -p "$B/lib/vio/ffi"
cp "$P"/lib/vio/ffi/*.dart             "$B/lib/vio/ffi/"
cp "$P"/lib/vio/pose/*.dart            "$B/lib/vio/pose/"
cp "$P"/lib/vio/render/*.dart          "$B/lib/vio/render/"
cp "$P"/assets/materials/*.filamat     "$B/assets/materials/"
# 2026-09-22(端到端拍摄探针 zero_arkit_capture_probe_page.dart):镜像范围再跟着依赖走一次。
#   lib/vio/render/zero_arkit_capture_probe_page.dart
#     → lib/vio/pose/vio_ar_pose_provider.dart(已镜像)
#         → lib/vio/capture/{zero_arkit_capture_runtime, zero_arkit_photo_api,
#                            zero_arkit_scale_provenance, camera_time_offset}.dart
#         → lib/vio/quality/{initialization_window, pose_confidence, …}.dart
#         → lib/official_dome/ar_pose.dart(ARPose / ARFrameSaveSpec / ARFrameSaveResult)
#         → lib/official_capture/metric_rescale.dart(→ lib/vio/quality/scale_observability.dart)
#   传递依赖(编译时冒出来的,逐个说明):
#     lib/vio/timebase/*.dart  ← camera_time_offset.dart 要 IosTimebaseChannel
#                                (ios_timebase_channel → clock_offset_estimator + timebase_contract;
#                                 整目录镜像,内部互相 import,单挑三个文件迟早漏)
#     lib/quality/quality_compute.dart ← lib/vio/quality/texture_sufficiency.dart 只要
#                                        它的一个常量 kQualitySignatureSide
#     lib/dome/ar_pose.dart    ← quality_compute.dart 要 FrameQualityReport
#                                (🔴 与 lib/official_dome/ar_pose.dart 是两个不同文件)
#   🔴 Swift 清单**不变**:PwVioTimebase.swift(1519 行、import ARKit)不镜像 ——
#      台架没有 pocketworld_vio_timebase 通道,PwDeviceMachine.prime() 在台架上如实 null,
#      机型由探针页 sysctlbyname 直读(见该页文件头)。PwZeroArkitGate.swift 也不要:
#      台架没有 ARKit,没有租约可争。
mkdir -p "$B/lib/vio/capture" "$B/lib/vio/quality" "$B/lib/vio/timebase" \
         "$B/lib/quality" "$B/lib/dome" "$B/lib/official_dome" "$B/lib/official_capture"
cp "$P"/lib/vio/capture/*.dart         "$B/lib/vio/capture/"
cp "$P"/lib/vio/quality/*.dart         "$B/lib/vio/quality/"
cp "$P"/lib/vio/timebase/*.dart        "$B/lib/vio/timebase/"
cp "$P"/lib/quality/quality_compute.dart          "$B/lib/quality/"
cp "$P"/lib/dome/ar_pose.dart                     "$B/lib/dome/"
cp "$P"/lib/official_dome/ar_pose.dart            "$B/lib/official_dome/"
cp "$P"/lib/official_capture/metric_rescale.dart  "$B/lib/official_capture/"
# 2026-09-20: 台架现在也编跨端 C++ 传输层(PwXrslamTransportCore.cpp 进了
# Runner 的 Sources)。2026-09-22: 加 PWJSONSafety.swift —— PwCameraSlot 的照片 sidecar 要它。不用拷 —— `$B/vendor/xrslam` 本来就是指向生产那棵树的
# 符号链接,天然逐字节一致。下面那道校验会把这条性质钉住。
for f in PwCameraSlot.swift PwMonotonicClock.swift PwImuSource.swift PwXrslamLive.swift PWJSONSafety.swift; do cp "$P/ios/Runner/$f" "$B/ios/Runner/"; done
bad=0
for f in "$B"/lib/vio/ffi/*.dart "$B"/lib/vio/pose/*.dart "$B"/lib/vio/render/*.dart \
         "$B"/lib/vio/capture/*.dart "$B"/lib/vio/quality/*.dart "$B"/lib/vio/timebase/*.dart; do
  rel="lib/vio/${f#*/lib/vio/}"
  cmp -s "$f" "$P/$rel" || { echo "🔴 不一致: $rel"; bad=1; }
done
for rel in lib/quality/quality_compute.dart lib/dome/ar_pose.dart \
           lib/official_dome/ar_pose.dart lib/official_capture/metric_rescale.dart; do
  cmp -s "$B/$rel" "$P/$rel" || { echo "🔴 不一致: $rel"; bad=1; }
done
for f in PwCameraSlot.swift PwMonotonicClock.swift PwImuSource.swift PwXrslamLive.swift PWJSONSafety.swift; do cmp -s "$B/ios/Runner/$f" "$P/ios/Runner/$f" || { echo "🔴 不一致: $f"; bad=1; }; done
for f in PwXrslamTransportCore.h PwXrslamTransportCore.cpp; do cmp -s "$B/vendor/xrslam/transport/$f" "$P/vendor/xrslam/transport/$f" || { echo "🔴 不一致: $f"; bad=1; }; done
# 镜像目录里不许有生产没有的文件(分叉的第一步就是多出一个文件)。
for d in lib/vio/ffi lib/vio/pose lib/vio/render lib/vio/capture lib/vio/quality lib/vio/timebase; do
  for f in "$B/$d"/*.dart; do
    [ -f "$P/$d/$(basename "$f")" ] || { echo "🔴 台架多出生产没有的文件: $d/$(basename "$f")"; bad=1; }
  done
done
[ $bad -eq 0 ] && echo "✅ 与生产逐字节一致"
exit $bad
