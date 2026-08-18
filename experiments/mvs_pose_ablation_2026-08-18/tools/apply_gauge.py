#!/usr/bin/env python3
"""把非参考臂的稠密云套上 gauge(相机光心 Umeyama 相似变换),写出对齐后的 PLY。

🔴 为什么必须先对齐:三套 COLMAP 重建的尺度/朝向/原点各自任意,不对齐比覆盖
   等于比"谁的世界坐标系凑巧更大",毫无意义。相似变换保形,云内几何一个字没动。

Umeyama 实现逐字取自 lightglue_spike/export_ply.py:39(不重写第二份)。
实测残差:P16k vs P8k 4.79mm,P16k vs P16kH 2.21mm —— 与 08-18 参考值吻合。
"""
import argparse, numpy as np, pycolmap as pc


def umeyama(src, dst):                      # ← export_ply.py:39 原样
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    C = b.T @ a / len(src)
    U, D, Vt = np.linalg.svd(C)
    S_ = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S_[2, 2] = -1
    R = U @ S_ @ Vt
    s = (D * np.diag(S_)).sum() / (a ** 2).sum() * len(src)
    return s, R, mu_d - s * R @ mu_s


def centers(work):
    r = pc.Reconstruction(f"{work}/sparse/0")
    return {im.name: np.asarray(im.projection_center())      # ← export_ply.py:63 同一 API
            for im in r.images.values() if im.has_pose}


DT = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
               ("r", "u1"), ("g", "u1"), ("b", "u1")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--ref", default="P16k")
    ap.add_argument("--arm", required=True)
    a = ap.parse_args()

    A, B = centers(f"{a.dir}/work_{a.ref}"), centers(f"{a.dir}/work_{a.arm}")
    k = sorted(set(A) & set(B))
    s, R, t = umeyama(np.array([B[i] for i in k]), np.array([A[i] for i in k]))
    res = np.linalg.norm(np.array([A[i] for i in k])
                         - (s * (np.array([B[i] for i in k]) @ R.T) + t), axis=1)
    print(f"  {a.arm}→{a.ref}  尺度 {s:.4f}  残差中位 {1000*np.median(res):.2f}mm "
          f"p90 {1000*np.percentile(res,90):.2f}mm  ({len(k)} 台相机)")

    f = open(f"{a.dir}/dense_{a.arm}.ply", "rb"); n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"): n = int(l.split()[-1])
        if l.strip() == b"end_header": break
    rec = np.fromfile(f, dtype=DT, count=n)
    xyz = np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)
    xyz = s * (xyz @ R.T) + t
    out = np.empty(n, dtype=DT)
    out["x"], out["y"], out["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    for c in "rgb": out[c] = rec[c]
    p = f"{a.dir}/aligned_{a.arm}.ply"
    with open(p, "wb") as g:
        g.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n"
                "property float x\nproperty float y\nproperty float z\n"
                "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                "end_header\n".encode())
        out.tofile(g)
    print(f"  → {p}  {n:,} 点")


if __name__ == "__main__":
    main()
