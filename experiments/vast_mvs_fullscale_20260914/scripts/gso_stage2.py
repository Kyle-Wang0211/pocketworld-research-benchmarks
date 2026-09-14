"""阶段2:把阶段1的 depth npy + 内外参写成 MVSNet/blend 格式,并出 pair.txt。
跑在 /venv/main(有 torchvision,能 import 官方 save_pfm)。
共视分数复用 tartanground2mvsnet 里已验证的官方复刻实现。
用法: gso_stage2.py <out_root> <scan>
"""
import sys, os, json, importlib.util
import numpy as np
OUT_ROOT, SCAN = sys.argv[1], sys.argv[2]
D = f"{OUT_ROOT}/{SCAN}"
Ds = np.load(f"{D}/_depths.npy")
m = json.load(open(f"{D}/_meta.json"))
Ks = [np.array(k) for k in m["K"]]; Es = [np.array(e) for e in m["E"]]
W, H, NV = m["W"], m["H"], m["NV"]

sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import save_pfm
os.makedirs(f"{D}/rendered_depth_maps", exist_ok=True)
for i in range(NV):
    z = Ds[i].copy(); z[~np.isfinite(z)] = 0.0; z[z > 1e4] = 0.0
    save_pfm(f"{D}/rendered_depth_maps/{i:08d}.pfm", z.astype(np.float32))
    v = z[z > 0]; dmin, dmax = float(v.min()), float(v.max())
    with open(f"{D}/cams/{i:08d}_cam.txt", "w") as f:
        f.write("extrinsic\n")
        for r in Es[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\nintrinsic\n")
        for r in Ks[i]: f.write(" ".join("%.9f" % x for x in r) + "\n")
        f.write("\n%f %f\n" % (dmin, dmax))

os.environ["DIFFMVS_DIR"] = "/root/diffmvs"
spec = importlib.util.spec_from_file_location("tg", "/root/tartanground2mvsnet.py")
tg = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ["tg"]
try: spec.loader.exec_module(tg)
except SystemExit: pass
sys.argv = _a

centers = [tg.cam_center_from_E(E) for E in Es]
sc = np.zeros((NV, NV))
for i in range(NV):
    zi = Ds[i]; mk = np.isfinite(zi) & (zi > 0) & (zi < 1e4)
    ys, xs = np.nonzero(mk)
    if len(xs) < 200: continue
    sel = np.random.default_rng(i).choice(len(xs), size=min(4000, len(xs)), replace=False)
    xs, ys = xs[sel], ys[sel]; d = zi[ys, xs]
    pc = np.linalg.inv(Ks[i]) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)
    pw = (np.linalg.inv(Es[i]) @ np.vstack([pc, np.ones(pc.shape[1])]))[:3].T
    for j in range(NV):
        if i != j: sc[i, j] = tg.calc_score_from_points(centers[i], centers[j], pw)
with open(f"{D}/cams/pair.txt", "w") as f:
    f.write("%d\n" % NV)
    for i in range(NV):
        o = [j for j in np.argsort(-sc[i]) if j != i][:10]
        f.write("%d\n%d " % (i, len(o)) + " ".join("%d %.6f" % (j, sc[i, j]) for j in o) + "\n")
os.remove(f"{D}/_depths.npy"); os.remove(f"{D}/_meta.json")
print("[STAGE2-DONE] %s | 共视非零 %d/%d" % (SCAN, int((sc > 0).sum()), NV * NV - NV), flush=True)
