#!/bin/bash
# 用法: run_apk.sh ROWS REPS [KERNEL] [EXTRA_ENV k=v;k=v] [TIMEOUT_S]
# 以 app 身份跑探针(Mate 10 的 Vulkan ICD 对 adb shell uid 不暴露设备),轮询 files/probe_out.txt 直到 PROBE_DONE。
set -u
PKG=com.kyle.pwprobe
ROWS=${1:-8192}; REPS=${2:-2}; KERNEL=${3:-}; EXTRA=${4:-}; TO=${5:-1200}
adb shell "run-as $PKG rm -f files/probe_out.txt" >/dev/null 2>&1
adb shell am force-stop $PKG >/dev/null 2>&1
adb logcat -c
adb shell input keyevent KEYCODE_WAKEUP   # 灭屏时 EMUI 不启 Activity
ES=""; [ -n "$KERNEL" ] && ES="$ES --es kernel $KERNEL"; [ -n "$EXTRA" ] && ES="$ES --es extra '$EXTRA'"   # adb shell 会吞空的 "" ⇒ am 报 Argument expected
adb shell "am start -n $PKG/.Main --ei rows $ROWS --ei reps $REPS $ES" 2>&1 | tr -d "\r" | grep -vE "^Starting|^$"
t0=$(date +%s)
while :; do
  out=$(adb shell "run-as $PKG cat files/probe_out.txt" 2>/dev/null)
  if echo "$out" | grep -q "PROBE_DONE"; then echo "$out"; exit 0; fi
  if ! adb shell "ps -A" 2>/dev/null | tr -d "\r" | grep -q " $PKG$"; then
    echo "### 进程消失 (crash?)  已有输出:"; echo "$out"
    echo "### logcat:"; adb logcat -d 2>/dev/null | grep -E "pwprobe|AndroidRuntime|DEBUG|libc |vulkan|Vulkan|dawn|Dawn" | tail -40; exit 2
  fi
  if (( $(date +%s) - t0 > TO )); then echo "### timeout ${TO}s  已有输出:"; echo "$out"; exit 3; fi
  sleep 3
done
