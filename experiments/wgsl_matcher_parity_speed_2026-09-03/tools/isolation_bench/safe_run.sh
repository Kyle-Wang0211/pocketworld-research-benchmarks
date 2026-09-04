#!/usr/bin/env bash
# safe_run.sh —— 跑任何手工改过的着色器台架都必须经这里
#
# 起因(2026-09-04 两次 GPU 挂死,都是我自己的 bug、都编译通过):
#   ① 切 MSL 变体时把列循环自增 `col0 += 32` 一起删掉 → 死循环
#   ② python 替换写出 `threadgroup int* __restrict cip = &cip[0];` → 野指针
# 一次挂死烧掉 11 分钟,并让整机 GPU 进入不可解释的降级态(2× 慢)。
#
# 三道闸:冒烟(小规模先跑,挂死 ~3 秒暴露) / 硬超时(perl alarm,macOS 无 GNU timeout)
#        / 阳性对照(参照核不合格就拒绝出数)
# 用法: [K=V ...] ./safe_run.sh <bench 可执行文件>
set -uo pipefail
BIN="${1:?用法: [K=V ...] safe_run.sh <bench>}"
SMOKE_TIMEOUT=${SMOKE_TIMEOUT:-20}
FULL_TIMEOUT=${FULL_TIMEOUT:-300}
PC_TARGET=${PC_TARGET:-3.87}
PC_TOL=${PC_TOL:-0.15}

TO() {  # TO <秒> <命令...>;超时杀整个进程组,退出码 142
  perl -e '$t=shift; $SIG{ALRM}=sub{ kill 9,-$$; exit 142 }; alarm $t;
           setpgrp(0,0); exec @ARGV' "$@"
}

echo "[闸1/3] 冒烟(NB=256,超时 ${SMOKE_TIMEOUT}s)——死循环/野指针会在这里暴露"
NB=256 TO "$SMOKE_TIMEOUT" "$BIN" >/tmp/smoke.log 2>&1
rc=$?
if [ $rc -ne 0 ]; then
  if [ $rc -eq 142 ]; then
    echo "🔴 冒烟超时被杀 —— 着色器很可能死循环或野指针。**不要重试**,先逐行核对改动处。"
  else
    echo "🔴 冒烟失败 rc=$rc"; tail -3 /tmp/smoke.log
  fi
  exit 1
fi
echo "[闸1/3] 通过"

echo "[闸2/3] 阳性对照:手写参照核须 ${PC_TARGET} ± ${PC_TOL}"
PC=$(TO 180 ./pc 2>/dev/null | tail -1 | grep -o 'min=[0-9.]*' | cut -d= -f2)
if [ -z "${PC:-}" ]; then echo "🔴 阳性对照没跑出来"; exit 1; fi
if [ "$(python3 -c "print(1 if abs($PC-$PC_TARGET)<=$PC_TOL else 0)")" != "1" ]; then
  echo "🔴 阳性对照 = $PC(健康 $PC_TARGET)⇒ 机器状态不对,**此刻任何时序结论都不算数**。"
  echo "   已排除:低电量模式 / 热 / CPU 争用 / 残留进程 / 驱动重置(recoveryCount=0)。"
  echo "   已知有效:重启。"
  exit 2
fi
echo "[闸2/3] 通过($PC)"

echo "[闸3/3] 正式测量(超时 ${FULL_TIMEOUT}s)"
TO "$FULL_TIMEOUT" "$BIN"
