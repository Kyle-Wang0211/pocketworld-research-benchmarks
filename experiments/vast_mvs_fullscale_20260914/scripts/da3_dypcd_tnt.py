#!/usr/bin/env python3
"""DA3-BASE @742 深度 → MonoMVSNet 官方 TNT-advanced dypcd 梯子(test_dypcd_tnt_adv.py,一行不改)。
🔴 这份的公式是**线性** rel_diff < i*rel_diff_base(DTU 那份是 log10)。两份官方实现不同,别混。
常数:adv 表里 6 个场景**全跑一遍**,不由我挑行 —— 点数报出来,肉眼选。
光度那一半仍是 DA3 官方门(conf 二值化 + conf_all=0.5)⇒ 与 DTU 臂、与 ③ 口径一致。
"""
import os, sys, shutil, math
import numpy as np
sys.path.insert(0, "/root/MonoMVSNet"); os.chdir("/root/MonoMVSNet")
ROOT = "/root/da3_dypcd"; SCAN = "scene0"; scn = f"{ROOT}/{SCAN}"; out = f"{ROOT}/out"
assert os.path.exists(f"{out}/depth_est/00000000.pfm"), "先跑 da3_dypcd.py 铺好输入"
shutil.copy(f"{scn}/pair.txt", f"{scn}/new_pair.txt")      # TNT 版读的是 new_pair.txt
sys.argv = ["x", "--testpath", ROOT, "--testlist", "/dev/null", "--outdir", out, "--loadckpt", "/dev/null"]
import importlib.util
spec = importlib.util.spec_from_file_location("dyp", "/root/MonoMVSNet/test_dypcd_tnt_adv.py")
dyp = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(dyp)
except SystemExit: pass
except Exception as ex: print("模块加载警告:", str(ex)[:140], flush=True)

D0 = np.load(sorted(__import__("glob").glob("/root/da3_r742b/exports/npz/*.npz"))[0])["depth"]
MED = float(np.median(D0[D0 > 0]))
ROWS = ["Auditorium", "Ballroom", "Courtroom", "Museum", "Palace", "Temple"]
res = {}
for name in ROWS:
    for d in ("s_all", "dist_all", "rel_diff_all", "fusion_view"):
        getattr(dyp, d)[SCAN] = getattr(dyp, d)[name]
    dyp.conf_all[SCAN] = 0.5            # conf 已二值化 ⇒ 等价于 DA3 官方 p40 门
    s = dyp.s_all[SCAN]; fv = dyp.fusion_view[SCAN]
    db = dyp.dist_all[SCAN]; rb = dyp.rel_diff_all[SCAN]
    print(f"\n===== {name}: s={s} fusion_view={fv} dist_base={db} rel_diff_base={rb} "
          f"| 最紧 i={s}: {s*db:.2f}px/{s*rb*MED*1000:.2f}mm@{s}票 "
          f"| i=10: {10*db:.2f}px/{10*rb*MED*1000:.2f}mm@10票", flush=True)
    ply = f"/root/da3_tnt_{name}.ply"
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        dyp.filter_depth(scn, scn, out, ply)
    vp = [float(l.split()[-1]) for l in buf.getvalue().split("\n") if l.startswith("valid_points")]
    from plyfile import PlyData
    n = len(PlyData.read(ply).elements[0].data)
    res[name] = n
    print(f"  final-mask 均值 {np.mean(vp):.4f}   点数 {n:,}", flush=True)
print("\n===== 汇总 =====", flush=True)
for k, v in sorted(res.items(), key=lambda kv: -kv[1]): print(f"  {k:12s} {v:>12,}", flush=True)
