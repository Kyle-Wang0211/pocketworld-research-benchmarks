#!/bin/bash
# 用法: run_apk.sh ROWS REPS [KERNEL] [EXTRA_ENV k=v;k=v] [TIMEOUT_S]
# 以 app 身份跑探针(Mate 10 的 Vulkan ICD 对 adb shell uid 不暴露设备),轮询 files/probe_out.txt 直到 PROBE_DONE。
set -u
PKG=com.kyle.pwprobe
ADB="adb -s ${PW_ADB_SERIAL:-192.168.1.11:5555}"   # 默认走 Wi-Fi adb;USB 用 PW_ADB_SERIAL=D3H7N18328002468
ROWS=${1:-8192}; REPS=${2:-2}; KERNEL=${3:-}; EXTRA=${4:-}; TO=${5:-1200}
$ADB shell "run-as $PKG rm -f files/probe_out.txt" >/dev/null 2>&1
$ADB shell am force-stop $PKG >/dev/null 2>&1
$ADB logcat -c
$ADB shell input keyevent KEYCODE_WAKEUP   # 灭屏时 EMUI 不启 Activity
ES=""; [ -n "$KERNEL" ] && ES="$ES --es kernel $KERNEL"; [ -n "$EXTRA" ] && ES="$ES --es extra '$EXTRA'"   # adb shell 会吞空的 "" ⇒ am 报 Argument expected
$ADB shell "am start -n $PKG/.Main --ei rows $ROWS --ei reps $REPS $ES" 2>&1 | tr -d "\r" | grep -vE "^Starting|^$"
t0=$(date +%s); sleep 3; miss=0   # 新装包首启有 dexopt,先等一拍;进程判失要连续两次
while :; do
  out=$($ADB shell "run-as $PKG cat files/probe_out.txt" 2>/dev/null)
  if echo "$out" | grep -q "PROBE_DONE"; then
    # 装机≠生效:对照编进 .so 的 TU sha 与 out_build_id.txt(最近一次 build_so.sh)
    want=$(cat "$(dirname "$0")/out_build_id.txt" 2>/dev/null); got=$(echo "$out" | grep -oE "^BUILD_ID [0-9a-f]+" | cut -d' ' -f2)
    if [ -n "$want" ] && [ "$want" != "$got" ]; then echo "### BUILD_ID 不一致:设备=$got 期望=$want(新 APK 没装?)"; echo "$out"; exit 4; fi
    echo "$out"; exit 0; fi
  if ! $ADB shell "ps -A" 2>/dev/null | tr -d "\r" | grep -q " $PKG$"; then miss=$((miss+1)); else miss=0; fi
  if [ $miss -ge 2 ]; then
    echo "### 进程消失 (crash?)  已有输出:"; echo "$out"
    echo "### logcat:"; $ADB logcat -d 2>/dev/null | grep -E "pwprobe|AndroidRuntime|DEBUG|libc |vulkan|Vulkan|dawn|Dawn" | tail -40; exit 2
  fi
  if (( $(date +%s) - t0 > TO )); then echo "### timeout ${TO}s  已有输出:"; echo "$out"; exit 3; fi
  sleep 3
done
