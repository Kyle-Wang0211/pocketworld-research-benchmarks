#!/usr/bin/env python3
"""单帧背投三方对照:同一帧 / 同一相机 / 同一内参。
判别问题:那面白墙,各家把它摆成什么形状。
  A) DAv2-Small 纯单目(仅用 2 参数 scale+shift 对齐到 MonoMVSNet 的深度, 形状全来自单目模型)
  B) MonoMVSNet 门后深度
  C) MVSAnywhere 完整版门后深度(分辨率不同, 单独出)
单帧云不受跨帧不一致影响, 墙平不平一眼可见。"""
import sys, os, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")

MONO = "/root/mono_only/dav2s"
GM   = "/root/regionmerge/gated_mono_noconf"
OUT  = "/root/single_frame"
os.makedirs(OUT, exist_ok=True)

def write_ply(path, V, C):
    with open(path, "wb") as f:
        f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\n"
                 "property float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n" % len(V)).encode())
        r = np.zeros(len(V), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        r["x"],r["y"],r["z"] = V[:,0],V[:,1],V[:,2]; r["r"],r["g"],r["b"] = C[:,0],C[:,1],C[:,2]
        r.tofile(f)

def backproject(d, K, E, col):
    keep = d > 0
    h, w = d.shape
    x, y = np.meshgrid(np.arange(w), np.arange(h))
    x, y, dd = x[keep], y[keep], d[keep]
    xyz = np.linalg.inv(K) @ (np.vstack((x, y, np.ones_like(x))) * dd)
    V = (np.linalg.inv(E) @ np.vstack((xyz, np.ones_like(x))))[:3].T.astype(np.float32)
    return V, col[keep].astype(np.uint8)

# 找白墙面积最大的帧: 亮 且 局部方差低
best = []
for f in sorted(glob.glob(f"{GM}/depth/*.npy")):
    i = int(os.path.basename(f)[:8])
    img = cv2.imread(f"{GM}/color/{i:08d}.png")
    if img is None: continue
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    var = cv2.Laplacian(g, cv2.CV_32F, ksize=3)
    wall = ((g > 150) & (np.abs(var) < 4)).mean()
    best.append((wall, i))
best.sort(reverse=True)
print("白墙占比最高的帧:", [(f"{i}", f"{w*100:.1f}%") for w, i in best[:5]])

for w, i in best[:3]:
    z = np.load(f"{GM}/cam/{i:08d}.npz"); K, E = z["K"], z["E"]
    col = cv2.imread(f"{GM}/color/{i:08d}.png")[:, :, ::-1]
    dref = np.load(f"{GM}/depth/{i:08d}.npy")
    V, C = backproject(dref, K, E, col); write_ply(f"{OUT}/f{i:03d}_monomvsnet.ply", V, C)

    disp = np.load(f"{MONO}/{i:08d}.npy")           # DAv2 输出的是相对反深度
    m = (dref > 0) & np.isfinite(disp)
    # 只用 2 个参数(尺度+平移)对齐到参考的反深度空间; 墙的形状完全来自单目模型
    A = np.stack([disp[m], np.ones(m.sum())], 1)
    coef, *_ = np.linalg.lstsq(A, 1.0 / dref[m], rcond=None)
    dm = 1.0 / np.clip(coef[0] * disp + coef[1], 1e-6, None)
    dm[(dm <= 0) | (dm > 50)] = 0
    V, C = backproject(dm, K, E, col); write_ply(f"{OUT}/f{i:03d}_dav2s.ply", V, C)
    print(f"  帧 {i}: 白墙 {w*100:.1f}% | MonoMVSNet {(dref>0).sum():,} 点 | DAv2-S {(dm>0).sum():,} 点 "
          f"| 拟合 a={coef[0]:.4f} b={coef[1]:.4f}")
print("DONE", OUT)
