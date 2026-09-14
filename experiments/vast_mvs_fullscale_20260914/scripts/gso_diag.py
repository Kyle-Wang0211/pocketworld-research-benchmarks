"""诊断:把重投影误差的分布打出来,并与「故意弄错的约定」对照。
不猜,看数。"""
import sys, numpy as np, glob, os
sys.argv = ["x"]
exec(open("/root/gso_render.py").read().split("# ---------------- 自证②")[0].replace(
    'MODEL, OUT_ROOT, SCAN = sys.argv[1], sys.argv[2], sys.argv[3]',
    'MODEL, OUT_ROOT, SCAN = "/root/gso_probe/Vtech_Roll_Learn_Turtle", "/root/gso_mvs", "diag"').replace(
    'NV = int(sys.argv[4]); SAMPLES = int(sys.argv[5]) if len(sys.argv) > 5 else 128',
    'NV = 12; SAMPLES = 64'))

def stat(i, j, flip=None):
    Ki, Ei, Di = Ks[i], Es[i], Ds[i]; Kj, Ej, Dj = Ks[j], Es[j], Ds[j]
    if flip == "E":   Ei = np.linalg.inv(Ei); Ej = np.linalg.inv(Ej)   # 阴性对照:用反了 world<->cam
    m = np.isfinite(Di) & (Di > 0) & (Di < 1e4)
    ys, xs = np.nonzero(m)
    sel = np.random.default_rng(0).choice(len(xs), size=min(6000, len(xs)), replace=False)
    xs, ys = xs[sel], ys[sel]; d = Di[ys, xs]
    pc = np.linalg.inv(Ki) @ (np.stack([xs, ys, np.ones_like(xs)]) * d)
    pw = np.linalg.inv(Ei) @ np.vstack([pc, np.ones(pc.shape[1])])
    pj = (Ej @ pw)[:3]; z = pj[2]; g = z > 1e-6
    uv = Kj @ (pj / np.where(g, z, 1))
    u = np.round(uv[0]).astype(int); v = np.round(uv[1]).astype(int)
    inb = g & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    dj = Dj[np.clip(v,0,H-1), np.clip(u,0,W-1)]
    ok = inb & np.isfinite(dj) & (dj > 0) & (dj < 1e4)
    if ok.sum() < 50: return None
    rel = np.abs(z[ok] - dj[ok]) / dj[ok]
    return dict(n=int(ok.sum()), p10=float(np.percentile(rel,10)), p50=float(np.median(rel)),
                frac1pct=float((rel < 0.01).mean()), frac01pct=float((rel < 0.001).mean()))

print("\n=== 正常约定 ===")
for j in (1, 2, 3, 6):
    r = stat(0, j)
    if r: print("  0->%-2d n=%-5d p10=%.5f p50=%.5f  <1%%占比=%.3f  <0.1%%占比=%.3f" % (j, r["n"], r["p10"], r["p50"], r["frac1pct"], r["frac01pct"]))
print("=== 阴性对照(故意把 world<->cam 用反) ===")
for j in (1, 2):
    r = stat(0, j, flip="E")
    if r: print("  0->%-2d n=%-5d p10=%.5f p50=%.5f  <1%%占比=%.3f" % (j, r["n"], r["p10"], r["p50"], r["frac1pct"]))
