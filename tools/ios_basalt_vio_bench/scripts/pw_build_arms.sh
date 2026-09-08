#!/bin/bash
# 两臂各编一个 bench app 到 ~/Developer/viobench-build,编完还原生产 .a
set -eo pipefail
T=$(cd "$(dirname "$0")/.." && pwd); V=~/Developer/pocketworld/vendor/xrslam/libs/ios-arm64; BD=~/Developer/viobench-build
for ARM in thrnogate thrbp; do
  echo "──── $ARM ────"; cp "$V/libxrslam_${ARM}_4beb1a9.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"
  DD="$BD/bench-dd-$ARM"; rm -rf "$DD"
  (cd "$T" && LANG=en_US.UTF-8 xcodebuild -project VIOReplacementBench.xcodeproj -scheme VIOReplacementBench -configuration Release -destination 'generic/platform=iOS' -derivedDataPath "$DD" -allowProvisioningUpdates build 2>&1 | grep -E "error:|BUILD (SUCCEEDED|FAILED)" | tail -3)
  APP="$DD/Build/Products/Release-iphoneos/VIOReplacementBench.app"; shasum -a 256 "$V/libxrslam_${ARM}_4beb1a9.a" | cut -d' ' -f1 > "$DD/ENGINE_A_SHA256"
  echo "  engine sha16 $(shasum -a 256 "$APP/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" | cut -c1-16)  .a $(cut -c1-16 "$DD/ENGINE_A_SHA256")"
done
cp "$V/libxrslam_generic_4beb1a9.a" "$T/Vendor/xrslam/lib/libxrslam_generic_4beb1a9.a"; (cd "$T" && sh scripts/verify_vendor.sh >/dev/null 2>&1 && echo "vendor 已还原,verify 绿")
