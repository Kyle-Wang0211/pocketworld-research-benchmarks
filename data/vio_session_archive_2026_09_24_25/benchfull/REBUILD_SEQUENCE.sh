#!/usr/bin/env bash
# 完整链 168 台架:重建与核验顺序(磁盘 ≥3 GiB 才跑;每步前 df,<2 GiB 立停)。只编不装。
set -euo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/benchfull
B=/Users/kaidongwang/Developer/arloopbench
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export FLUTTER_XCODE_DEBUG_INFORMATION_FORMAT=dwarf      # 不出 dSYM(省盘;可执行文件不变)
export FLUTTER_XCODE_LD_GENERATE_MAP_FILE=YES            # 链接图,核 Dawn 目标文件来源
need() { a=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$a" -ge $((3*1024*1024)) ] || { echo "盘只剩 $((a/1024)) MiB,停"; exit 3; }; }
MAP_GLOB="$HOME/Library/Developer/Xcode/DerivedData/Runner-*/Build/Intermediates.noindex/Runner.build/Profile-iphoneos/Runner.build/Runner-LinkMap-normal-arm64.txt"
APP="$B/build/ios/iphoneos/Runner.app"
cd "$B"
# 0) 镜像自证(不拷 LOD)
PW_BENCH_LOD_VERIFY_ONLY=1 ./.sync_from_integration.sh
# 1) B:完整链包(最重,原生全量;之后两步只重编 Dart AOT)
need; flutter build ios --profile --dart-define=PW_FULL_CHAIN_BENCH=true -v > "$S/build_B.log" 2>&1
"$S/verify_binary.sh" "$APP" 1 $(ls $MAP_GLOB 2>/dev/null | head -1) | tee "$S/verify_B.txt"
# 2) A1:台架默认包(VIO 各页进 AOT、完整链 Dart 被树摇、原生照样链)
need; flutter build ios --profile -v > "$S/build_A1.log" 2>&1
"$S/verify_binary.sh" "$APP" 0 | tee "$S/verify_A1.txt"
# 3) A2:LOD 页包(LodDebugPage 进 AOT)
need; flutter build ios --profile --dart-define=PW_LOD_BENCH=true -v > "$S/build_A2.log" 2>&1
"$S/verify_binary.sh" "$APP" 0 | tee "$S/verify_A2.txt"
# 4) 最后回到 B,留在 build/ios/iphoneos 的就是完整链包
need; flutter build ios --profile --dart-define=PW_FULL_CHAIN_BENCH=true -v > "$S/build_B_final.log" 2>&1
"$S/verify_binary.sh" "$APP" 1 $(ls $MAP_GLOB 2>/dev/null | head -1) | tee "$S/verify_B_final.txt"
# 链接图很大,核完即删(它在 DerivedData 中间目录里)
rm -f $MAP_GLOB
