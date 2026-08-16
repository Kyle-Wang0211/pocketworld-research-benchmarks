#!/usr/bin/env bash
# APDe WGSL → iPhone 真机 bench:手搓 .app 打包 + 签名
#
# 为什么不用 Xcode 工程:这是纯 Metal compute 打点,不需要 Flutter/CocoaPods。
# 手搓包全程可见、无构建系统风险(pod install 撞 Ruby4 那类坑一个都碰不到)。
#
# ⚠️ bundle id 用独立的 com.kyle.apdebench,与产品 com.kyle.PocketWorld 无关,
#    装它不会碰产品 app 及其拍摄数据。
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BD="$HERE/_build"
# 🔴 .app 必须打在**非 File Provider 卷**上。progecttwo 在同步卷上,
#    目录会被自动打上 com.apple.FinderInfo,codesign 直接拒签
#    ("resource fork, Finder information, or similar detritus not allowed"),
#    而且 xattr -c 清掉后会立刻回来 —— 不是清不干净,是卷在写。
STAGE="${APDE_BENCH_STAGE:-/private/tmp/apde_bench_stage}"
mkdir -p "$STAGE"
APP="$STAGE/APDeBench.app"
BUNDLE_ID="com.kyle.apdebench"
TEAM="26AH7V448L"
FIXTURE="${1:-$HERE/_data/sub30}"

rm -rf "$APP"; mkdir -p "$APP"

# ── 1. 主二进制 ──
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min=17.0 \
  -std=c++17 -fobjc-arc -O2 \
  "$HERE/host/apde_ios_bench.mm" \
  -framework Metal -framework Foundation -framework UIKit \
  -o "$APP/APDeBench"

# ── 2. Info.plist ──
cat > "$APP/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>APDeBench</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>APDeBench</string>
  <key>CFBundleDisplayName</key><string>APDe Bench</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>MinimumOSVersion</key><string>17.0</string>
  <key>UIDeviceFamily</key><array><integer>1</integer></array>
  <key>UILaunchScreen</key><dict/>
  <key>UISupportedInterfaceOrientations</key>
  <array><string>UIInterfaceOrientationPortrait</string></array>
</dict></plist>
PLIST
plutil -convert binary1 "$APP/Info.plist"

# ── 3. 资源:metallib + binding 表 + fixture ──
cp "$BD/new/ios/apde_ios.metallib" "$APP/"
cp "$BD/new/bindings.txt"          "$APP/"
for f in images.f16 cams.f32 neighbors.i32; do cp "$FIXTURE/$f" "$APP/"; done

# ── 4. 描述文件:挑通配的 TEAM.*(任意 bundle id 都能签)──
PROF=""
for p in ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*.mobileprovision; do
  aid=$(security cms -D -i "$p" 2>/dev/null | plutil -extract Entitlements.application-identifier raw - 2>/dev/null || true)
  if [ "$aid" = "$TEAM.*" ]; then PROF="$p"; break; fi
done
[ -n "$PROF" ] || { echo "❌ 找不到通配描述文件 $TEAM.*"; exit 1; }
echo "描述文件: $(basename "$PROF")"
cp "$PROF" "$APP/embedded.mobileprovision"

# ── 5. 权限(从描述文件取,只保留签名必需的三项)──
cat > "$BD/bench.entitlements" <<ENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>application-identifier</key><string>$TEAM.$BUNDLE_ID</string>
  <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  <key>get-task-allow</key><true/>
</dict></plist>
ENT

# ── 6. 签名 ──
# ⚠️ 从 Finder/网络下载来的文件带扩展属性,codesign 会直接拒签
#    ("resource fork, Finder information, or similar detritus not allowed")
xattr -cr "$APP"
codesign --force --sign "Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)" \
         --entitlements "$BD/bench.entitlements" --timestamp=none "$APP"
codesign -dv "$APP" 2>&1 | head -4
echo "✅ → $APP  ($(du -sh "$APP" | cut -f1))"
