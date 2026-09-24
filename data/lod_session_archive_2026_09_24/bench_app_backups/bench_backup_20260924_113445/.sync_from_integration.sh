#!/usr/bin/env bash
# bench 里的 vio 代码是生产的**镜像**,不是分叉。真源在 pocketworld。
# 改动一律改生产,然后跑这个同步过来。跑完会自证逐字节一致。
set -euo pipefail
# 2026-09-23(录制回放):真源从 zero-arkit-preview-20260922(feat/ios-zero-arkit-integration @ cfe7d44)
#   挪到 bench-replay-20260923(feat/bench-replay,= feat/per-frame-k-host 之上)。那条线是这条线的祖先
#   (cfe7d44 → +13 个逐帧内参提交 → 回放),所以不是换分叉,是往前走。要临时从别的树同步:
#   PW_BENCH_SYNC_SOURCE=<pocketworld 工作树> ./.sync_from_integration.sh
#   🔴 从更老的树同步会把 PwXrslamLive.swift 换回没有回放入口的版本 ⇒ 台架编不过;
#      下面「多出生产没有的文件」那道闸会先把回放文件点名出来。
P="${PW_BENCH_SYNC_SOURCE:-/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-replay-20260923}"; B=/Users/kaidongwang/Developer/arloopbench
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
# 2026-09-23(对焦三臂 PwFocusArms.swift):镜像范围再跟着依赖走一次。
#   ios/Runner/PwFocusArms.swift
#     → vendor/pw_af/pw_af_c.{h,cpp}(C ABI 门面,经 Runner-Bridging-Header.h 进 Swift)
#         → vendor/pw_af/{af_scan,focus_measure,lens_scale}.{h,cpp}(算法本体)
#   Dart 侧 lib/vio/ffi/pw_focus_ffi.dart 已被 `cp lib/vio/ffi/*.dart` 覆盖。
#   🔴 vendor/pw_af **不能**像 vendor/xrslam 那样做符号链接:xrslam 那个链的是
#      ~/Developer/pocketworld 那棵树,而 pw_af 只存在于本分支 ⇒ 老老实实拷贝,
#      下面那道 cmp 把「逐字节一致」钉住。
# 2026-09-23(录制回放 bench_replay_page.dart):镜像范围再跟着依赖走一次。
#   lib/vio/render/bench_replay_page.dart(render/*.dart 已整目录镜像)
#     → lib/vio/replay/{bench_replay_controller, bench_replay_native}.dart   ← 新目录,整目录镜像
#         → lib/vio/ffi/{xrslam_config, xrslam_live_ffi}.dart、lib/vio/capture/camera_time_offset.dart(已镜像)
#   Dart 走 FFI 到原生:
#     ios/Runner/PwBenchReplay.swift            回放器 + 5 个 pw_bench_replay_* C ABI
#       → PwBenchReplayRecording.swift          录制装载(BasaltVIOBench DeviceRecordingLoader 的移植)
#       → PwBenchReplayScheduler.swift          节拍器(BasaltVIOBench ReplayScheduler 逐字照抄)
#       → PwBenchReplayEngineProbe.{h,c}        只读 BODY_POSE + 求解遥测(桥接头 import;.c 要
#                                               vendor/xrslam/include/XRSLAM.h,HEADER_SEARCH_PATHS 已有)
#       → PwXrslamLive.swift                    ON 臂通路本身(已镜像;回放入口 beginReplay /
#                                               pushReplayImu / 逐帧观察者就加在这个文件里)
#   构建期:ios/scripts/stamp_bench_engine_identity.sh(Runner 的「Stamp Bench Engine Identity」阶段调用,
#     抄生产 ios/scripts/stamp_runtime_identity.sh 的引擎臂那一半)。
#   🔴 pbxproj / Podfile / 桥接头 / main.dart 是台架自己的文件,不在镜像范围(同 PwFocusArms 那次)。
mkdir -p "$B/lib/vio/replay" "$B/ios/scripts"
cp "$P"/lib/vio/replay/*.dart "$B/lib/vio/replay/"
cp "$P"/ios/scripts/stamp_bench_engine_identity.sh "$B/ios/scripts/"
for f in PwCameraSlot.swift PwMonotonicClock.swift PwImuSource.swift PwXrslamLive.swift PWJSONSafety.swift PwFocusArms.swift \
         PwBenchReplay.swift PwBenchReplayRecording.swift PwBenchReplayScheduler.swift \
         PwBenchReplayEngineProbe.h PwBenchReplayEngineProbe.c; do cp "$P/ios/Runner/$f" "$B/ios/Runner/"; done
# 2026-09-23:`$B/vendor/xrslam` 这个符号链接**跟着 P 走**。此前它一直指向 ~/Developer/pocketworld
#   (主检出),而 P 是另一个工作树 —— 下面那道传输层 cmp 之所以一直过,只是因为两边碰巧同版本。
#   逐帧内参之后传输层多了 PushCameraAndRunRawWithIntrinsics,pfk 归档也只在 P 这条线上,
#   指向主检出就既编不过也链不上。现在显式指向 P,下面那道 cmp 照旧把「逐字节一致」钉住。
ln -sfn "$P/vendor/xrslam" "$B/vendor/xrslam"
mkdir -p "$B/vendor/pw_af"
cp "$P"/vendor/pw_af/*.h "$P"/vendor/pw_af/*.cpp "$B/vendor/pw_af/"
cp "$P"/vendor/pw_af/LICENSE.libcamera-BSD-2-Clause "$B/vendor/pw_af/"
bad=0
for f in "$B"/lib/vio/ffi/*.dart "$B"/lib/vio/pose/*.dart "$B"/lib/vio/render/*.dart \
         "$B"/lib/vio/capture/*.dart "$B"/lib/vio/quality/*.dart "$B"/lib/vio/timebase/*.dart \
         "$B"/lib/vio/replay/*.dart; do
  rel="lib/vio/${f#*/lib/vio/}"
  cmp -s "$f" "$P/$rel" || { echo "🔴 不一致: $rel"; bad=1; }
done
for rel in lib/quality/quality_compute.dart lib/dome/ar_pose.dart \
           lib/official_dome/ar_pose.dart lib/official_capture/metric_rescale.dart; do
  cmp -s "$B/$rel" "$P/$rel" || { echo "🔴 不一致: $rel"; bad=1; }
done
for f in PwCameraSlot.swift PwMonotonicClock.swift PwImuSource.swift PwXrslamLive.swift PWJSONSafety.swift PwFocusArms.swift \
         PwBenchReplay.swift PwBenchReplayRecording.swift PwBenchReplayScheduler.swift \
         PwBenchReplayEngineProbe.h PwBenchReplayEngineProbe.c; do cmp -s "$B/ios/Runner/$f" "$P/ios/Runner/$f" || { echo "🔴 不一致: $f"; bad=1; }; done
cmp -s "$B/ios/scripts/stamp_bench_engine_identity.sh" "$P/ios/scripts/stamp_bench_engine_identity.sh" \
  || { echo "🔴 不一致: ios/scripts/stamp_bench_engine_identity.sh"; bad=1; }
[ "$(readlink "$B/vendor/xrslam")" = "$P/vendor/xrslam" ] \
  || { echo "🔴 vendor/xrslam 没指向真源:$(readlink "$B/vendor/xrslam")"; bad=1; }
for f in "$P"/vendor/pw_af/*.h "$P"/vendor/pw_af/*.cpp "$P"/vendor/pw_af/LICENSE.libcamera-BSD-2-Clause; do
  cmp -s "$B/vendor/pw_af/$(basename "$f")" "$f" || { echo "🔴 不一致: vendor/pw_af/$(basename "$f")"; bad=1; }
done
# 台架的 vendor/pw_af 里不许有生产没有的文件。
for f in "$B"/vendor/pw_af/*; do
  [ -f "$P/vendor/pw_af/$(basename "$f")" ] || { echo "🔴 台架多出生产没有的文件: vendor/pw_af/$(basename "$f")"; bad=1; }
done
for f in PwXrslamTransportCore.h PwXrslamTransportCore.cpp; do cmp -s "$B/vendor/xrslam/transport/$f" "$P/vendor/xrslam/transport/$f" || { echo "🔴 不一致: $f"; bad=1; }; done
# 镜像目录里不许有生产没有的文件(分叉的第一步就是多出一个文件)。
for d in lib/vio/ffi lib/vio/pose lib/vio/render lib/vio/capture lib/vio/quality lib/vio/timebase lib/vio/replay; do
  for f in "$B/$d"/*.dart; do
    [ -f "$P/$d/$(basename "$f")" ] || { echo "🔴 台架多出生产没有的文件: $d/$(basename "$f")"; bad=1; }
  done
done
[ $bad -eq 0 ] && echo "✅ 与生产逐字节一致"
exit $bad
