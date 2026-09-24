#!/bin/bash
# Infinigen Indoors 成本探枪。
# 🔴 独立 venv, 绝不碰正在训练的 /venv/main；纯 CPU, GPU 留给训练。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root/infinigen

# 🔴 Infinigen 锁死 Python 3.11 (系统是 3.12) => 用 uv 装的 3.11 建 venv
PY311=/.uv/python_install/cpython-3.11-linux-x86_64-gnu/bin/python3.11
if [ ! -x /root/ig_venv2/bin/python ]; then
  LOG "建独立 venv (Python 3.11)"
  $PY311 -m venv /root/ig_venv2
  /root/ig_venv2/bin/pip install -q --upgrade pip setuptools wheel 2>&1 | tail -2
fi
LOG "venv python: $(/root/ig_venv2/bin/python -V)"
P=/root/ig_venv2/bin/python

if ! $P -c 'import infinigen' 2>/dev/null; then
  LOG "安装 infinigen (含 bpy/Blender, 会比较久)"
  $P -m pip install -e . 2>&1 | tail -10
fi

LOG "版本自证"
$P -c 'import infinigen, bpy; print("  infinigen", infinigen.__version__, "| bpy", bpy.app.version_string)' 2>&1 | tail -3

LOG "计时: 单间 DiningRoom coarse (官方 HelloRoom.md 报 ~8 分钟 CPU)"
rm -rf /root/ig_probe
T0=$(date +%s)
$P -m infinigen_examples.generate_indoors \
  --seed 0 --task coarse \
  --output_folder /root/ig_probe/coarse \
  -g fast_solve.gin singleroom.gin \
  -p compose_indoors.terrain_enabled=False \
  > /root/ig_probe_coarse.log 2>&1
RC=$?
T1=$(date +%s)
LOG "coarse 结束 rc=$RC 用时 $((T1-T0)) 秒 = $(( (T1-T0)/60 )) 分"
tail -6 /root/ig_probe_coarse.log | sed 's/^/  /'
ls -la /root/ig_probe/coarse/ 2>/dev/null | head -8
touch /root/IGPROBE_COARSE_DONE
