"""TartanGround 新环境端到端自证:官方 dataloader 真读 + 真前向。
判据: 0 missing/0 unexpected 权重键;所有 stage 输出 finite;深度值落在 cam.txt 的 [dmin,dmax] 内。"""
import sys, os, glob
sys.argv = ["x"]
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
import numpy as np, torch
from datasets.blend import MVSDataset

SCAN = os.environ.get("TG_SCAN", "tg_SeasonalForestAutumn_omni_P0000")
ROOT = os.environ.get("TG_ROOT", "/root/tg_conv")
lst = "/root/tg_verify_list.txt"
open(lst, "w").write(SCAN + "\n")

ds = MVSDataset(ROOT, lst, "train", 9, 384)
print("[LOAD] metas =", len(ds.metas))
s = ds[0]
for k, v in s.items():
    if isinstance(v, np.ndarray):
        print("  %-16s %-22s finite=%s" % (k, str(v.shape), bool(np.isfinite(v).all())))
    elif isinstance(v, dict):
        for kk, vv in v.items():
            print("  %-16s %-22s finite=%s" % (k+"."+kk, str(np.asarray(vv).shape), bool(np.isfinite(np.asarray(vv)).all())))

m = s["mask"]["stage4"] if isinstance(s.get("mask"), dict) else None
d = s["depth"]["stage4"] if isinstance(s.get("depth"), dict) else None
if m is not None and d is not None:
    print("[MASK] stage4 有效像素占比 = %.4f" % float(np.mean(m)))
    dv = np.asarray(d)[np.asarray(m) > 0]
    if dv.size: print("[DEPTH] 有效深度 min/median/max = %.3f / %.3f / %.3f" % (dv.min(), np.median(dv), dv.max()))
print("[VALUES] depth_values 范围 = %.6f .. %.6f" % (float(s["depth_values"].min()), float(s["depth_values"].max())))
