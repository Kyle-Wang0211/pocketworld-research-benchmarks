#!/bin/bash
# Infinigen Indoors 完整安装 (generate_indoors 是 legacy 管线, 需要 terrain 原生编译)
# 依据 docs/source/Installation.md:44, :88-99
# 🔴 独立 venv (Python 3.11), 纯 CPU, 不碰 /venv/main 和 GPU。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
export DEBIAN_FRONTEND=noninteractive
P=/root/ig_venv2/bin/python
PIP=/root/ig_venv2/bin/pip

LOG "apt 依赖 (Installation.md:44)"
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq wget cmake g++ libgles2-mesa-dev libglew-dev libglfw3-dev libglm-dev zlib1g-dev >/dev/null 2>&1
LOG "  cmake $(cmake --version | head -1 | awk '{print $3}')  g++ $(g++ --version | head -1 | awk '{print $NF}')"

cd /root/infinigen
LOG "完整安装 + 编译 terrain (Installation.md:99)"
T0=$(date +%s)
INFINIGEN_MINIMAL_INSTALL=False INFINIGEN_INSTALL_TERRAIN=True \
  $PIP install -e ".[infinigen1]" > /root/ig_install.log 2>&1
RC=$?
T1=$(date +%s)
LOG "  安装 rc=$RC 用时 $(( (T1-T0)/60 )) 分"
[ $RC -ne 0 ] && tail -15 /root/ig_install.log | sed 's/^/    /'

LOG "terrain 自证"
$P -c 'import infinigen.terrain as t; print("  terrain import ok")' 2>&1 | tail -2

LOG "计时: 单间 coarse"
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
if [ $RC -eq 0 ]; then
  LOG "✅ coarse 成功 用时 $((T1-T0)) 秒 = $(( (T1-T0)/60 )) 分 $(( (T1-T0)%60 )) 秒"
  du -sh /root/ig_probe/coarse | sed 's/^/  产物 /'
else
  LOG "🔴 coarse 失败 rc=$RC 用时 $((T1-T0)) 秒"
  tail -14 /root/ig_probe_coarse.log | sed 's/^/    /'
fi
touch /root/IGFULL_DONE
