#!/bin/bash
# pw_prod_heat_split.sh <条件标签> <阶段>  —— 量生产 app 的热量构成
#
# 为什么是这个形态(而不是逐秒曲线):
#   • 热度只能通过启动 bench app 读 preflight.json 拿到(pw_thermometer.sh),
#     开 app 会把生产切到后台 ⇒ **不可能在生产运行期间采样**。
#   • 生产自己只在"降频/快门档翻转"那一刻记热态,没有周期曲线;而实测
#     168 次会话的 pw_device_log.txt 里这两类事件**一次都没出现过**,
#     不能当尺子。
#   • 苹果只暴露 4 档(nominal/fair/serious/critical),没有数值温度。
# ⇒ 尺子 = 会话结束时的热档 + **回到 nominal 所需时间**(累积热量的代理)。
#   两个条件用同一把尺子,差值才是重建管线额外贡献的热。
#
# 用法:
#   pw_prod_heat_split.sh <标签> pre    会话前:确认 nominal(必须 0 才放行)
#   pw_prod_heat_split.sh <标签> post   会话后:立刻测峰值,再等到回 nominal
set -uo pipefail
LABEL=${1:?用法: pw_prod_heat_split.sh <标签> <pre|post>}; PHASE=${2:?pre 或 post}
D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}
S=$(cd "$(dirname "$0")" && pwd)
OUT=~/Developer/viobench-recordings/prod-heat; mkdir -p "$OUT"
LOG="$OUT/${LABEL}.log"
say() { echo "$(date '+%H:%M:%S') $*" | tee -a "$LOG"; }

# 存活闸(与真机测量同一套判据)
P=$(xcrun devicectl device info processes --device "$D" 2>/dev/null | wc -l)
[ "$P" -gt 200 ] || { say "✗ 进程列表 $P 行,设备异常,拒绝"; exit 1; }

case "$PHASE" in
  pre)
    say "══════ $LABEL 会话前 ══════"
    t=$("$S/pw_thermometer.sh" | tail -1); say "起跑热态=$t (进程 $P 行)"
    [ "$t" = "0" ] || { say "✗ 不是 nominal,先降温再开始(两个条件必须同起点)"; exit 2; }
    say "✓ 可以开始:请打开 PocketWorld 按约定动作用满 300 秒,结束后回到桌面并告诉我"
    ;;
  post)
    say "══════ $LABEL 会话后 ══════"
    t=$("$S/pw_thermometer.sh" | tail -1); say "结束热态(峰值代理)=$t"
    T0=$(date +%s)
    if [ "$t" = "0" ]; then say "回 nominal 用时 = 0 s(结束时已是 nominal)"; else
      for i in $(seq 1 40); do
        sleep 60
        c=$("$S/pw_thermometer.sh" | tail -1); e=$(( $(date +%s) - T0 ))
        say "  +${e}s thermal=$c"
        [ "$c" = "0" ] && { say "★ $LABEL 回 nominal 用时 = ${e} s(结束热态=$t)"; break; }
      done
    fi
    ;;
  *) say "阶段只能是 pre 或 post"; exit 1;;
esac
