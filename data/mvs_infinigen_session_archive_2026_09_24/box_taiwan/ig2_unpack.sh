#!/bin/bash
set -e
[ -x /root/cvdpack_venv/bin/cvdpack ] || { python3 -m venv /root/cvdpack_venv >/dev/null 2>&1 || /venv/main/bin/python -m venv /root/cvdpack_venv; /root/cvdpack_venv/bin/pip install -q cvdpack huggingface_hub 2>&1 | tail -2; }
/root/cvdpack_venv/bin/cvdpack --help >/dev/null 2>&1 && echo "cvdpack 已装: $(/root/cvdpack_venv/bin/pip show cvdpack 2>/dev/null | grep Version)"
cd /root/ig2fly && rm -rf out tmp
T0=$(date +%s)
/root/cvdpack_venv/bin/cvdpack unpack --input https://huggingface.co/datasets/infinigen/infinigen2-flying-indoors/tree/main/PartA --output out --tmp_folder tmp --hf_staging upfront --subset scene=30377061_0 gt_type=rgb,depth 2>&1 | tail -5
echo "解包用时 $(( $(date +%s)-T0 ))s"; ls out; for d in out/*; do echo "$d: $(ls $d/CameraLeft | head -3 | tr '\n' ' ') 共 $(ls $d/CameraLeft | wc -l) 个; 右目 $(ls $d/CameraRight 2>/dev/null | wc -l) 个"; done | head -8
/root/cvdpack_venv/bin/python - <<'PY'
import numpy as np, glob
f=sorted(glob.glob("/root/ig2fly/out/*traj0/CameraLeft/depth_0000.npy"))[0]; d=np.load(f); print("深度", d.shape, d.dtype, "范围 %.3f–%.3f m"%(np.nanmin(d),np.nanmax(d)), "nan占比 %.4f"%np.isnan(d).mean())
u=np.unique(d[np.isfinite(d)]); 
for z in (1.0,2.0,3.0,5.0):
    i=np.searchsorted(u,z); 
    if 0<i<len(u): print("  在 %.0f m 附近相邻两个可表示值的间距 = %.3f mm"%(z,(u[i]-u[i-1])*1000))
PY
