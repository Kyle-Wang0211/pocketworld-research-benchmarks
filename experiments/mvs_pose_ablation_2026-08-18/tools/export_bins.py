#!/usr/bin/env python3
"""把三臂稠密云导成全分辨率二进制,供 fetch 式查看器直读。**零降采样。**

格式抄 `_artifacts/casdiffmvs_fixture97_20260817/bin/`(那套已实测扛得住 22M/59M 点):
  <臂>.pos  float32 xyz 交错     <臂>.col  uint8 rgb 交错     meta.json  n/center/ext

🔴 为什么不能像 build_page.py 那样 base64 内嵌:三臂合计 9000 万点,内嵌后 >1.2 GB,
   浏览器打不开。全分辨率与「单文件双击可开」二者不可兼得 —— 这里选全分辨率,
   因为判据是肉眼看稠密,抽稀 1/20 的页面看起来跟稀疏云没区别(2026-08-18 用户指出)。

坐标共享同一 center/scale(取参考臂),三窗完全同坐标系;云本身已 gauge 对齐。
"""
import argparse, json, os
import numpy as np

DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])


def read(p):
    f = open(p, "rb"); n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"): n = int(l.split()[-1])
        if l.strip() == b"end_header": break
    return np.fromfile(f, dtype=DT, count=n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default="P16k"); ap.add_argument("--arms", default="P16k,P8k,P16kH")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    meta = {}
    for w in a.arms.split(","):
        src = f"{a.dir}/dense_{w}.ply" if w == a.ref else f"{a.dir}/aligned_{w}.ply"
        rec = read(src)
        pos = np.stack([rec["x"], rec["y"], rec["z"]], 1).astype("<f4")
        col = np.stack([rec["r"], rec["g"], rec["b"]], 1).astype(np.uint8)
        pos.tofile(f"{a.out}/{w}.pos"); np.ascontiguousarray(col).tofile(f"{a.out}/{w}.col")
        # center/ext 用 1%/99% 分位而非 min/max —— 一颗飞点就能把包围盒撑大,
        # 那样三窗初始缩放会被离群点支配,场景缩成一个点。
        lo, hi = np.percentile(pos, [1, 99], axis=0)
        # 视轴参数与 build_local_page.py 同口径:target = 中位数,radius = 到中位数距离的 p95。
        # 用中位/分位而非 min/max —— 一颗飞点就能把包围盒撑大,那样初始缩放被离群点支配。
        med = np.median(pos, 0)
        rad = float(np.percentile(np.linalg.norm(pos - med, axis=1), 95))
        meta[w] = {"n": int(len(pos)), "center": ((lo + hi) / 2).tolist(),
                   "ext": (hi - lo).tolist(),
                   "med": med.astype(float).tolist(), "radius": rad}
        print(f"  {w}: {len(pos):,} 点  "
              f"{(pos.nbytes + col.nbytes)/1e6:.0f} MB", flush=True)
        del rec, pos, col
    json.dump(meta, open(f"{a.out}/meta.json", "w"))


if __name__ == "__main__":
    main()
