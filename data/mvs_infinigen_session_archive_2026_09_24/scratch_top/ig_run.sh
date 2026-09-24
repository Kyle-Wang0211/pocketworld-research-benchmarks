#!/bin/bash
# Infinigen Indoors 成本探枪 —— 自动补缺失依赖后计时。
# 🔴 独立 venv (Python 3.11), 纯 CPU, 不碰 /venv/main 和 GPU。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
PIP=/root/ig_venv2/bin/pip
cd /root/infinigen

# 模块名 -> pip 包名(少数不同名的)
declare -A MAP=( [gin]=gin-config [cv2]=opencv-python [skimage]=scikit-image [sklearn]=scikit-learn \
                 [PIL]=pillow [yaml]=pyyaml [OpenEXR]=OpenEXR [Imath]=OpenEXR [pyrender]=pyrender \
                 [submitit]=submitit [einops]=einops [numba]=numba [shapely]=shapely )

for i in $(seq 1 14); do
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
    LOG "✅ coarse 成功, 用时 $((T1-T0)) 秒 = $(( (T1-T0)/60 )) 分 $(( (T1-T0)%60 )) 秒"
    du -sh /root/ig_probe/coarse 2>/dev/null | sed 's/^/  产物: /'
    ls /root/ig_probe/coarse/ | head -8 | sed 's/^/    /'
    break
  fi
  MISS=$(grep -oE "ModuleNotFoundError: No module named '[^']+'" /root/ig_probe_coarse.log | tail -1 | sed "s/.*'\(.*\)'/\1/")
  if [ -z "$MISS" ]; then
    LOG "🔴 非缺模块错误 (rc=$RC), 用时 $((T1-T0)) 秒:"
    tail -12 /root/ig_probe_coarse.log | sed 's/^/    /'
    break
  fi
  PKG=${MAP[$MISS]:-$MISS}
  LOG "缺 $MISS -> 装 $PKG"
  $PIP install -q "$PKG" 2>&1 | grep -iE "^ERROR" | head -2
done
touch /root/IGRUN_DONE
