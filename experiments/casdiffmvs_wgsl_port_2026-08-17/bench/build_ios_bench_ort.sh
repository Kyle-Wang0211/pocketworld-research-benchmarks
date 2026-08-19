#!/usr/bin/env bash
# CasDiffMVS ORT-WebGPU → iPhone 真机 bench:手搓 .app 打包 + 签名(方案 A:dylib)
# 改自 apde_wgsl_port_2026-08-14/tools/build_ios_bench.sh(验证过的手搓 .app 路数)。
#
# 方案 A:libonnxruntime.1.29.0.dylib(WebGPU EP 已在内)进 .app/Frameworks/,
#         可执行加 -rpath @executable_path/Frameworks。
# ⚠️ bundle id 用独立的 com.kyle.casdiffbench,与产品 com.kyle.PocketWorld 无关,
#    装它不会碰产品 app 及其拍摄数据。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# ── 输入(全部已核实在位)──
ORT_LIB_DIR="$HOME/ort_ios_build/build_ios/Release/Release-iphoneos"
ORT_DYLIB="$ORT_LIB_DIR/libonnxruntime.1.29.0.dylib"     # install name = @rpath/libonnxruntime.1.dylib
ORT_INC="$HOME/ort_ios_build/onnxruntime/include/onnxruntime/core/session"
RES_DIR="/Users/kaidongwang/Documents/progecttwo/_artifacts/ios_bench_20260819"
MODEL="$RES_DIR/casdiffmvs_v5.onnx"
INPUTS="$RES_DIR/inputs8.bin"

# 🔴 .app 必须打在**非 File Provider 卷**上。progecttwo 在同步卷上,
#    目录会被自动打上 com.apple.FinderInfo,codesign 直接拒签
#    ("resource fork, Finder information, or similar detritus not allowed"),
#    xattr -c 清掉后会立刻回来 —— 不是清不干净,是卷在写。
STAGE="${CASDIFF_BENCH_STAGE:-/private/tmp/casdiff_bench_stage}"
APP="$STAGE/CasDiffBench.app"
BUNDLE_ID="com.kyle.casdiffbench"
TEAM="26AH7V448L"
IDENTITY="Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)"
MINOS="16.3"   # 与 dylib 的 LC_BUILD_VERSION minos 对齐

rm -rf "$APP"; mkdir -p "$APP/Frameworks"

# ── 1. 编译 ──
# bench_main.cc 原样同编,只用 -Dmain=bench_run 改入口名(别改文件本身)。
CXXFLAGS=(-arch arm64 -miphoneos-version-min="$MINOS" -std=c++17 -O2 -I"$ORT_INC")
xcrun -sdk iphoneos clang++ "${CXXFLAGS[@]}" -Dmain=bench_run \
  -c "$HERE/bench_main.cc" -o "$STAGE/bench_main.o"
xcrun -sdk iphoneos clang++ "${CXXFLAGS[@]}" -fobjc-arc \
  -c "$HERE/ios_shell_main.mm" -o "$STAGE/ios_shell_main.o"

# ── 2. 链接(方案 A)──
# 直接对着 dylib 链,linker 记录它的 install name(@rpath/libonnxruntime.1.dylib);
# 运行时靠 -rpath @executable_path/Frameworks 找到包内副本。
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min="$MINOS" \
  "$STAGE/ios_shell_main.o" "$STAGE/bench_main.o" \
  "$ORT_DYLIB" \
  -framework UIKit -framework Foundation \
  -Wl,-rpath,@executable_path/Frameworks \
  -o "$APP/CasDiffBench"

# ── 3. dylib 进包:按 install name 命名(bundle 内不放符号链)──
cp "$ORT_DYLIB" "$APP/Frameworks/libonnxruntime.1.dylib"

# ── 4. 资源:model + inputs ──
cp "$MODEL" "$INPUTS" "$APP/"

# ── 5. Info.plist ──
cat > "$APP/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>CasDiffBench</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>CasDiffBench</string>
  <key>CFBundleDisplayName</key><string>CasDiff Bench</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>MinimumOSVersion</key><string>$MINOS</string>
  <key>UIDeviceFamily</key><array><integer>1</integer></array>
  <key>UILaunchScreen</key><dict/>
  <key>UIFileSharingEnabled</key><true/>
  <key>LSSupportsOpeningDocumentsInPlace</key><true/>
  <key>UISupportedInterfaceOrientations</key>
  <array><string>UIInterfaceOrientationPortrait</string></array>
</dict></plist>
PLIST
plutil -convert binary1 "$APP/Info.plist"

# ── 6. 描述文件:挑通配的 TEAM.*(任意 bundle id 都能签)──
PROF=""
for p in ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*.mobileprovision; do
  aid=$(security cms -D -i "$p" 2>/dev/null | plutil -extract Entitlements.application-identifier raw - 2>/dev/null || true)
  if [ "$aid" = "$TEAM.*" ]; then PROF="$p"; break; fi
done
[ -n "$PROF" ] || { echo "❌ 找不到通配描述文件 $TEAM.*"; exit 1; }
echo "描述文件: $(basename "$PROF")"
cp "$PROF" "$APP/embedded.mobileprovision"

# ── 7. 权限(只保留签名必需的三项)──
cat > "$STAGE/bench.entitlements" <<ENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>application-identifier</key><string>$TEAM.$BUNDLE_ID</string>
  <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  <key>get-task-allow</key><true/>
</dict></plist>
ENT

# ── 8. 签名:xattr 清干净后,🔴 先 dylib 后 .app(顺序反了 .app 的 seal 会失效)──
xattr -cr "$APP"
codesign --force --sign "$IDENTITY" --timestamp=none "$APP/Frameworks/libonnxruntime.1.dylib"
codesign --force --sign "$IDENTITY" \
         --entitlements "$STAGE/bench.entitlements" --timestamp=none "$APP"

# ── 9. 验证 ──
echo "── codesign(dylib)──";   codesign -vv "$APP/Frameworks/libonnxruntime.1.dylib"
echo "── codesign(.app)──";    codesign -vv "$APP"
echo "── otool -L / rpath ──";  otool -L "$APP/CasDiffBench" | sed -n '1,8p'
otool -l "$APP/CasDiffBench" | grep -A2 LC_RPATH | grep path || true
echo "── lipo ──";              lipo -info "$APP/CasDiffBench" "$APP/Frameworks/libonnxruntime.1.dylib"
echo "── 内容清单 ──";           (cd "$STAGE" && find CasDiffBench.app -type f -exec du -h {} + | sort -k2)
echo "✅ → $APP  ($(du -sh "$APP" | cut -f1))"
