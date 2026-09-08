#!/bin/bash
# pw_install_arm.sh <thrnogate|thrbp> —— 带闸的安装 + 身份核对
set -u; ARM=$1; D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}
APP=~/Developer/viobench-build/bench-dd-$ARM/Build/Products/Release-iphoneos/VIOReplacementBench.app
P=$(xcrun devicectl device info processes --device "$D" 2>/dev/null)
[ "$(echo "$P" | wc -l)" -gt 50 ] || { echo "进程列表异常,拒绝装机"; exit 1; }
echo "$P" | grep -qi PocketWorld && { echo "PW 在跑,拒绝装机"; exit 1; }
xcrun devicectl device install app --device "$D" "$APP" 2>&1 | grep -E "App installed|rror" | head -1
echo "installed $ARM: engine sha16 $(shasum -a 256 "$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" | cut -c1-16)  app sha16 $(shasum -a 256 "$APP/VIOReplacementBench" | cut -c1-16)"
