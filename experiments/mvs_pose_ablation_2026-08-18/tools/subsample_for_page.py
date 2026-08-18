#!/usr/bin/env python3
"""为并排页抽稀稠密云。**只影响看,不影响交付** —— dense_*.ply / aligned_*.ply 全量不动。

🔴 三臂必须用**同一抽样率**(不是同一点数)。按率抽是空间无偏的,相对密度和覆盖
   都按比例保住;若改成"每臂都抽到 150 万点",就等于把密度差异归一化掉,
   而密度差异正是这个实验要看的东西之一。

为什么不能全量上页:9 字节/点 × 3000 万 × 3 臂,base64 后 >1 GB,浏览器打不开。
"""
import argparse, numpy as np

DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--ref", default="P16k")
    ap.add_argument("--arms", default="P16k,P8k,P16kH")
    ap.add_argument("--rate", type=int, default=20, help="保留 1/rate")
    ap.add_argument("--seed", type=int, default=20260818)
    a = ap.parse_args()
    for w in a.arms.split(","):
        src = f"{a.dir}/dense_{w}.ply" if w == a.ref else f"{a.dir}/aligned_{w}.ply"
        f = open(src, "rb"); n = None
        while True:
            l = f.readline()
            if l.startswith(b"element vertex"): n = int(l.split()[-1])
            if l.strip() == b"end_header": break
        rec = np.fromfile(f, dtype=DT, count=n)
        rng = np.random.default_rng(a.seed)            # 同种子同率,臂间可比
        keep = rng.random(n) < (1.0 / a.rate)
        out = np.ascontiguousarray(rec[keep])
        p = f"{a.dir}/page_{w}.ply"
        with open(p, "wb") as g:
            g.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(out)}\n"
                    "property float x\nproperty float y\nproperty float z\n"
                    "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                    "end_header\n".encode())
            out.tofile(g)
        print(f"  {w}: {n:,} → {len(out):,} 点 (1/{a.rate})  {p}")

if __name__ == "__main__":
    main()
