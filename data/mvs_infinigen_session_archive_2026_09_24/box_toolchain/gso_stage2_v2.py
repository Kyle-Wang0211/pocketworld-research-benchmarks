"""阶段2 v2: depth npy + 内外参 -> MVSNet/blend 格式 + pair.txt。
  深度范围: colmap2mvsnet.py 的 1%/99% (zs_sorted[int(len*.01)] / [int(len*.99)]) —— v1 用 min/max 无出处
  共视分数: tartanground2mvsnet.calc_score_from_points (colmap2mvsnet calc_score 逐字), 点 = 步长 8 规则网格像素反投影
            (8 = CasDiffMVS stage1 1/8 分辨率, blend.py:127) —— v1 随机 4000 无出处
  源视图数: 10 (colmap2mvsnet.py sorted_score[:10])
用法: gso_stage2_v2.py <out_root> <scan>
"""
import sys, os, json, importlib.util
import numpy as np
OUT_ROOT, SCAN = sys.argv[1], sys.argv[2]
D = f"{OUT_ROOT}/{SCAN}"
Ds = np.load(f"{D}/_depths.npy"); m = json.load(open(f"{D}/_meta.json"))
Ks = [np.array(k) for k in m["K"]]; Es = [np.array(e) for e in m["E"]]; W, H, NV = m["W"], m["H"], m["NV"]
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import save_pfm
GRID, NSRC = 8, 10
for i in range(NV):
    z = Ds[i].copy(); z[~np.isfinite(z)] = 0.0; z[z > 1e4] = 0.0
    save_pfm(f"{D}/rendered_depth_maps/{i:08d}.pfm", z.astype(np.float32))
    zs = np.sort(z[z > 0]); dmin, dmax = float(zs[int(len(zs) * .01)]), float(zs[int(len(zs) * .99)])
    with open(f"{D}/cams/{i:08d}_cam.txt", "w") as f:
        f.write("extrinsic\n")
        for r in Es[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\nintrinsic\n")
        for r in Ks[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\n%f %f\n" % (dmin, dmax))
os.environ["DIFFMVS_DIR"] = "/root/diffmvs"
spec = importlib.util.spec_from_file_location("tg", "/root/tartanground2mvsnet.py")
tg = importlib.util.module_from_spec(spec); _a = sys.argv; sys.argv = ["tg"]
try: spec.loader.exec_module(tg)
except SystemExit: pass
sys.argv = _a
centers = [tg.cam_center_from_E(E) for E in Es]
sc = np.zeros((NV, NV))
for i in range(NV):
    zi = Ds[i]; mk = np.isfinite(zi) & (zi > 0) & (zi < 1e4)
    ys, xs = np.nonzero(mk); g = ((ys % GRID) == 0) & ((xs % GRID) == 0); xs, ys = xs[g], ys[g]
    if len(xs) < 20: continue
    d = zi[ys, xs]
    pc = np.linalg.inv(Ks[i]) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)
    pw = (np.linalg.inv(Es[i]) @ np.vstack([pc, np.ones(pc.shape[1])]))[:3].T
    for j in range(NV):
        if i != j: sc[i, j] = tg.calc_score_from_points(centers[i], centers[j], pw)
with open(f"{D}/cams/pair.txt", "w") as f:
    f.write("%d\n" % NV)
    for i in range(NV):
        o = [j for j in np.argsort(-sc[i]) if j != i and sc[i, j] > 0][:NSRC]
        f.write("%d\n%d " % (i, len(o)) + " ".join("%d %.6f" % (j, sc[i, j]) for j in o) + "\n")
os.remove(f"{D}/_depths.npy"); os.remove(f"{D}/_meta.json")
print("[STAGE2-DONE] %s | 共视非零 %d/%d" % (SCAN, int((sc > 0).sum()), NV * NV - NV), flush=True)
