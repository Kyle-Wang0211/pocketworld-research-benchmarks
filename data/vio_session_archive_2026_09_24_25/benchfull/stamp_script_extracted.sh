# [pw][full-chain 2026-09-24] 台架自有。把 Dart 侧 const 开关 PW_FULL_CHAIN_BENCH(--dart-define)的取值
# 盖进产物 Info.plist 的 PWFullChainBench,AppDelegate 据此决定是否注册生产 168 的 Runner 内插件。
# 单一真源 = DART_DEFINES(Generated.xcconfig,base64 逗号分隔),不另设原生开关,两边不会各说各话。
v=NO
for d in $(printf %s "${DART_DEFINES:-}" | tr , ' '); do
  if [ "$(printf %s "$d" | /usr/bin/base64 -D 2>/dev/null)" = PW_FULL_CHAIN_BENCH=true ]; then v=YES; fi
done
plist="$TARGET_BUILD_DIR/$INFOPLIST_PATH"
/usr/libexec/PlistBuddy -c "Delete :PWFullChainBench" "$plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :PWFullChainBench bool $v" "$plist"
echo "PW_FULL_CHAIN_BENCH native switch = $v"
