#!/bin/bash
# 印度箱预检:环境直传后逐项核对,任一项失败即退出非零
set -e
PY=/root/ig_venv2/bin/python
echo "[1] 解释器链接"; readlink -f $PY; $PY -c "import sys; print(sys.version)"
echo "[2] bpy"; $PY -c "import bpy; print('bpy', bpy.app.version_string)"
echo "[3] 单卡钉住后 Cycles 设备(应恰好 1 张 OPTIX)"
CUDA_VISIBLE_DEVICES=7 $PY - <<'PYEOF'
import bpy
p = bpy.context.preferences.addons['cycles'].preferences
p.compute_device_type = 'OPTIX'; p.get_devices()
ds = [d for d in p.devices if d.type == 'OPTIX']
print('OPTIX 设备数', len(ds), [d.name for d in ds]); assert len(ds) == 1
PYEOF
echo "[4] Infinigen 导入"; $PY -c "import infinigen, infinigen.datagen.manage_jobs, infinigen_examples.generate_indoors; print('infinigen', infinigen.__version__, infinigen.__file__)"
echo "[5] PR #506 补丁在位"; grep -c has_var_keyword /root/infinigen/src/infinigen/core/constraints/example_solver/room/decorate.py
echo "[6] 配置文件在位"; for g in local_256GB monocular blender_gt indoor_background_configs fast_solve singleroom multiview_stereo; do find /root/infinigen/src -name "$g.gin" | grep -q . && echo "  $g ok" || { echo "  $g 缺失"; exit 1; }; done
echo "[7] 转换器"; DIFFMVS_DIR=/root/diffmvs_full /venv/main/bin/python /root/infinigen_to_blend.py --help | head -3
echo "[8] 显卡"; nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
echo "预检全部通过"
