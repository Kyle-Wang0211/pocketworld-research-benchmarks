# ── 2026-09-24(完整重建链 168):独立的一段,上面 VIO 段(P)与 LOD 段(L)一个字不动 ─────────────
#   真源 = pocketworld 工作树 bench-full-chain-168(分支 bench/full-chain-168):
#     86a45cf = pw-dense-stage 工作树原样快照(1a43510 + 18 个未提交改动 + 未跟踪出货文件,2137 文件逐字节对上);
#     8437faf = 其上唯一一处改动:ios-arm64 PWOfficialSfm 换成 168 包里实际出货的那份核(源码树 vendor 的是 09-08 旧版)。
#   以后的生产补丁(位姿信任标志 / 跟踪会话切分 / 核内图像证据注册 + pwofficial_add_jpeg_frame_v2 / 核内 Sim3+闸 /
#   删 Dart SCALE-ANCHOR / 特征提取 GPU 模糊修复)一律先落在 pocketworld 的分支上,再用本段同步进来。
#   要临时从别的树同步:PW_BENCH_FULL_CHAIN_SOURCE=<pocketworld 工作树> ./.sync_from_integration.sh
#   只核不改(阴性对照 / 查台架有没有被改过):PW_BENCH_FULL_CHAIN_VERIFY_ONLY=1 ./.sync_from_integration.sh
#   镜像方式(逐项说明):
#     pw_full_chain → F                      符号链接。台架 pubspec 的 path 依赖 pocketworld_flutter 指向它:
#                                            生产 lib/ + packages/ + pubspec 原样当一个包用,包名与生产同,
#                                            与台架自己的 lib/vio 镜像(来自 bench-replay)互不相撞。
#     vendor/{aether_ffi,official_sfm,pw_dense,lepton_jpeg} → F/vendor/*    符号链接(同 vendor/xrslam 的做法;
#                                            二进制大,不拷)。Podfile 的三个生产 pod 与 lepton 链接行经它取。
#     ios/Vendor → F/ios/Vendor              符号链接。JXL 静态库/头、Zpaq 源码与许可、NativeCore 许可;
#                                            pbxproj 按生产原样的相对路径(Vendor/...)引用。
#     ios/Runner/<生产原生源文件>            拷贝 + cmp(同上面 VIO 段 Swift 的做法):清单见 fc_runner_files。
#     assets/models/DamagedHelmet.glb、assets/ibl/default_env_ibl.ktx → F/assets/...   符号链接:
#                                            生产代码按根键读的只有这两份(main.dart:875、live_model_view.dart:257)。
#   🔴 vendor/xrslam 仍跟 VIO 段走(bench-replay);168 自己的传输层是它的子集(差异:逐帧内参入口 + 账本),
#      台架只能编一份传输层 ⇒ 完整链的影子 XRSLAM 用 bench-replay 那份。见适配清单。
#   🔴 PWJSONSafety.swift 两段共用:VIO 段从 P 拷,这里只核它与 F 逐字节相同,不一致就报警(不拷,免得两段互相覆盖)。
#   🔴 pbxproj / Podfile / 桥接头 / AppDelegate / main.dart / pubspec 仍是台架自己的文件,不在镜像范围。
F="${PW_BENCH_FULL_CHAIN_SOURCE:-/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-full-chain-168}"
fc_runner_files="AetherTexturePlugin.swift MetalRenderer.swift OfficialAetherARKitPlugin.swift
OfficialArchiveBackgroundTask.swift OfficialReconUmbrella.swift PwARCameraLease.swift PwVioCapability.swift
PwVioSlamFeeder.swift PwVioThermal.swift PwVioTimebase.swift pw_jxl_bridge.h pw_jxl_bridge.mm
pw_zpaq_bridge.h pw_zpaq_bridge.cpp pw_sqlite_descriptor_transform.h pw_sqlite_descriptor_transform.cpp
PrivacyInfo.xcprivacy TestFixtures/test_scene.jpg"
fc_links="pw_full_chain:.
vendor/aether_ffi:vendor/aether_ffi
vendor/official_sfm:vendor/official_sfm
vendor/pw_dense:vendor/pw_dense
vendor/lepton_jpeg:vendor/lepton_jpeg
ios/Vendor:ios/Vendor
assets/models/DamagedHelmet.glb:assets/models/DamagedHelmet.glb
assets/ibl/default_env_ibl.ktx:assets/ibl/default_env_ibl.ktx"
echo "完整链真源: $F @ $(git -C "$F" rev-parse --short HEAD 2>/dev/null || echo '?')" \
     "(未提交改动 $(git -C "$F" status --porcelain 2>/dev/null | wc -l | tr -d ' ') 个)"
if [ "${PW_BENCH_FULL_CHAIN_VERIFY_ONLY:-0}" != 1 ]; then
  for f in $fc_runner_files; do mkdir -p "$B/ios/Runner/$(dirname "$f")"; cp "$F/ios/Runner/$f" "$B/ios/Runner/$f"; done
  while IFS=: read -r dst src; do
    mkdir -p "$B/$(dirname "$dst")"
    if [ "$src" = . ]; then ln -sfn "$F" "$B/$dst"; else ln -sfn "$F/$src" "$B/$dst"; fi
  done <<< "$fc_links"
fi
fbad=0
for f in $fc_runner_files; do cmp -s "$B/ios/Runner/$f" "$F/ios/Runner/$f" || { echo "🔴 完整链不一致: ios/Runner/$f"; fbad=1; }; done
cmp -s "$B/ios/Runner/PWJSONSafety.swift" "$F/ios/Runner/PWJSONSafety.swift" \
  || { echo "🔴 PWJSONSafety.swift:VIO 真源与完整链真源已分叉,台架只能编一份 —— 先在 pocketworld 里对齐"; fbad=1; }
while IFS=: read -r dst src; do
  if [ "$src" = . ]; then want="$F"; else want="$F/$src"; fi
  [ "$(readlink "$B/$dst")" = "$want" ] || { echo "🔴 $dst 没指向完整链真源:$(readlink "$B/$dst")"; fbad=1; }
  [ -e "$B/$dst" ] || { echo "🔴 $dst 指向的真源不存在:$want"; fbad=1; }
done <<< "$fc_links"
# 真源里 ios/Runner 的生产原生源文件不许有清单外的(漏镜像的第一步就是真源多出一个台架没编的文件)。
#   AppDelegate/SceneDelegate/Info.plist/entitlements/桥接头/GeneratedPluginRegistrant 是台架自己的(对应改法见适配清单);
#   PWJSONSafety.swift 由上面那道 cmp 管。
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  case "$rel" in
    AppDelegate.swift|SceneDelegate.swift|Info.plist|Runner.entitlements|Runner-Bridging-Header.h|PWJSONSafety.swift|GeneratedPluginRegistrant.*) continue;;
  esac
  printf '%s\n' $fc_runner_files | grep -Fxq -- "$rel" || { echo "🔴 真源 ios/Runner 多出完整链清单外的文件: $rel"; fbad=1; }
done <<< "$(cd "$F/ios/Runner" && find . -type f ! -path './Assets.xcassets/*' ! -path './Base.lproj/*' | sed 's|^\./||' | LC_ALL=C sort)"
if [ $fbad -eq 0 ]; then
  echo "✅ 完整链与真源逐字节一致($(printf '%s\n' $fc_runner_files | wc -l | tr -d ' ') 个拷贝文件 + $(printf '%s\n' "$fc_links" | wc -l | tr -d ' ') 个符号链接)"
else
  bad=1
fi
