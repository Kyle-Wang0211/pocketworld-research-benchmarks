#!/bin/bash
# gate_and_install_159.sh <app> <expected on-device .app name>
# = pw_ship.sh cmd_install's five gates, copied, plus the one fix the 156 install recorded: 闸③ reads the rotated
# device log (official_pw_device_log.1.txt) in front of the current one, otherwise a fresh rotation blinds the
# positive control. Never uninstalls, never launches.
set -uo pipefail
APP="$1"; EXPECT="$2"
D=1B290474-D354-5B4C-AAB0-0805AC5DC832; BID=com.kyle.PocketWorld
BKROOT=$HOME/Developer/pw_backups/pw102_20260906
die() { echo "🔴 $*" >&2; exit 1; }
[ -d "$APP" ] || die "包不存在:$APP"
device_app_name() {
  local j; j=$(mktemp)
  xcrun devicectl device info apps --device "$D" --bundle-id "$BID" --json-output "$j" >/dev/null 2>&1 || { rm -f "$j"; return 2; }
  local n; n=$(python3 -c "
import json
try:
    a=json.load(open('$j'))['result']['apps']; print(a[0]['url'].rstrip('/').split('/')[-1] if a else '')
except Exception: print('')"); rm -f "$j"; [ -n "$n" ] || return 2; printf '%s\n' "$n"
}
echo "=== 闸0 基线身份复核(期望机上是 $EXPECT) ==="
CUR=$(device_app_name) || die "探针失效:读不到机上包身份"
echo "机上 = $CUR"; [ "$CUR" = "$EXPECT" ] || die "机上不是 $EXPECT ⇒ 被别的线覆盖过,停"
echo "=== 闸B 装前备份对账(逐场比条数) ==="
BK=$(mktemp)
xcrun devicectl device info files --device "$D" --domain-type appDataContainer --domain-identifier "$BID" --subdirectory Documents --json-output "$BK" >/dev/null 2>&1 || { rm -f "$BK"; die "拉设备清单失败 ⇒ 判据失效"; }
python3 - "$BK" "$BKROOT" <<'PY'
import json,os,glob,sys
files=json.load(open(sys.argv[1]))['result']['files']; caps={}
for f in files:
    n=f.get('name','')
    if n.startswith('captures_official/cap_'): caps[n.split('/')[1]]=caps.get(n.split('/')[1],0)+1
if not caps: print("🔴 一场都没解析出来 ⇒ 探针失效"); sys.exit(2)
root=sys.argv[2]; bad=[]
for c,n in sorted(caps.items()):
    h=glob.glob(f'{root}/*/Documents/captures_official/{c}')
    best=max((sum(len(fs)+len(ds) for _,ds,fs in os.walk(x))+1) for x in h) if h else 0
    if best<n: bad.append((c,n,best))
print(f"设备 {len(caps)} 场,逐场比条数")
if bad:
    print("🔴 以下会话未进备份或不完整,拒绝装机:")
    for c,n,b in bad: print(f"   {c}  设备 {n} / 本地 {b}")
    sys.exit(1)
print("✓ 全部已在备份里")
PY
rc=$?; rm -f "$BK"; [ $rc -eq 0 ] || exit $rc
echo "=== 闸③ 近 5 分钟无采集/重建活动(当前日志 + 轮转日志) ==="
rm -f /tmp/pw159_devlog.txt /tmp/pw159_devlog1.txt
xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier "$BID" --source Documents/official_pw_device_log.txt --destination /tmp/pw159_devlog.txt >/dev/null 2>&1 || die "拉日志失败 ⇒ 判据失效"
xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier "$BID" --source Documents/official_pw_device_log.1.txt --destination /tmp/pw159_devlog1.txt >/dev/null 2>&1 || true
cat /tmp/pw159_devlog1.txt /tmp/pw159_devlog.txt 2>/dev/null > /tmp/pw159_devlog_all.txt
LAST=$(grep -E "worker up|session created|shutter ticket|add_frame|finalize|RefineGlobalBA" /tmp/pw159_devlog_all.txt | tail -1)
[ -n "$LAST" ] || die "日志里一条活动都没匹配到 ⇒ 阳性对照失败,拒绝装机"
TS=$(echo "$LAST" | cut -d' ' -f1); AGE=$(( $(date +%s) - $(date -j -f "%Y-%m-%dT%H:%M:%S" "${TS%.*}" +%s 2>/dev/null || echo 0) ))
echo "最后活动 $TS,距今 ${AGE}s"; [ "$AGE" -gt 300 ] || die "距今不足 300 s ⇒ 可能正在拍或在重建,拒绝装机"
echo "=== 闸①② 紧贴 install ==="
P=$(xcrun devicectl device info processes --device "$D" 2>/dev/null); N=$(echo "$P" | wc -l | tr -d ' '); echo "进程表 $N 行"
[ "$N" -gt 50 ] || die "进程列表异常 ⇒ 判据失效"
tries=0
while echo "$P" | grep -qiE 'PocketWorld|Runner'; do
  PID=$(echo "$P" | grep -iE 'PocketWorld|Runner' | awk '{print $1}' | head -1); tries=$((tries+1))
  [ "$tries" -le 3 ] || die "连关 3 次仍在跑(PID $PID)⇒ 它多半正忙,拒绝装机"
  echo "闸② app 在跑(PID $PID)—— 第 $tries 次关闭后台(terminate)"
  xcrun devicectl device process terminate --device "$D" --pid "$PID" >/dev/null 2>&1 || true; sleep 2
  P=$(xcrun devicectl device info processes --device "$D" 2>/dev/null); N=$(echo "$P" | wc -l | tr -d ' '); [ "$N" -gt 50 ] || die "进程列表异常"
done
[ "$tries" -eq 0 ] && echo "闸② app 不在跑" || echo "闸② 已关闭,进程表 $N 行"
echo "✓ 五道闸全过 —— 立即安装(原位覆盖,不卸载、不启动) $(date +%T)"
xcrun devicectl device install app --device "$D" "$APP" 2>&1 | grep -E "installed|error|Error" | head -3
echo "=== 装后核对 ==="
AFTER=$(device_app_name) || die "装后读不到包身份"
echo "机上 = $AFTER"; [ "$AFTER" = "$(basename "$APP")" ] && echo "✅ INSTALL_DONE $(date +%T)" || die "装后机上不是 $(basename "$APP")"
