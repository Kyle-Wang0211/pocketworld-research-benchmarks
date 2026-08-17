#!/usr/bin/env python3
"""给三臂重建补真彩、统一 gauge、导出 PLY。

⚠️ 关于 gauge:三臂是三次独立的增量建图,SfM 的尺度/旋转/原点本就是任意的,
不对齐就没法并排看(可能一个是倒的)。这里**只用相机光心**做 Umeyama 相似变换
把 A/B 对到 CONTROL 的 gauge —— 相机是同一批物理相机,这是修 gauge,不是拿
Sim3 去掩盖质量差异;相似变换保形,每朵云内部的相对几何一个字没动。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pycolmap as pc

# 默认是本机(Mac)那套目录名;租的机器上用 --arms 传另一套。
# ⚠️ IMGDIR 原来指向 /private/tmp 的 scratchpad,重启后被系统清空。现在用仓内 b28_named/
#    (按 DB 的 images.name 指向 frames/ 真实解码帧的软链,由 b28_frame_map.json 生成)。
_DEFAULT = "CONTROL=work_b28_control,ARM_A_SIFT_LG=work_b28_armA," \
           "ARM_B2_ALIKED_TUNED=work_b28_armB2,ARM_D_HYBRID=work_b28_armD," \
           "ARM_P_B2_PRUNED=work_b28_armP,ARM_R_RACO=work_b28_armR"

_ap = argparse.ArgumentParser()
_ap.add_argument("--arms", default=_DEFAULT, help="标签=工作目录,逗号分隔。第一个是 gauge 基准")
_ap.add_argument("--images", default="b28_named")
_args = _ap.parse_args()
IMGDIR = _args.images
_ALL = [tuple(x.split("=", 1)) for x in _args.arms.split(",") if x]
# 只导已经建出图的臂(被中途停掉的臂不该让整条导出挂掉)
ARMS = [(l, w) for l, w in _ALL if (Path(w) / "sparse").is_dir()]
REF = ARMS[0][0] if ARMS else None


def load(work):
    d = Path(work) / "sparse"
    return pc.Reconstruction(str(sorted(p for p in d.iterdir() if p.is_dir())[0]))


def umeyama(src, dst):
    """求 s,R,t 使 s*R*src + t ≈ dst(带尺度的相似变换)。"""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    C = b.T @ a / len(src)
    U, D, Vt = np.linalg.svd(C)
    S_ = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S_[2, 2] = -1
    R = U @ S_ @ Vt
    s = (D * np.diag(S_)).sum() / (a ** 2).sum() * len(src)
    t = mu_d - s * R @ mu_s
    return s, R, t


def main():
    recs = {}
    for lab, work in ARMS:
        r = load(work)
        n = r.extract_colors_for_all_images(IMGDIR)
        recs[lab] = r
        print(f"[{lab}] 取色 {'成功' if n else '⚠️ 返回 False'}  点 {r.num_points3D():,}", flush=True)

    ref = recs[REF]
    ref_c = {i: im.projection_center() for i, im in ref.images.items() if im.has_pose}

    for lab, r in recs.items():
        xyz = np.array([p.xyz for p in r.points3D.values()])
        rgb = np.array([p.color for p in r.points3D.values()], dtype=np.uint8)
        if lab != REF:
            cur = {i: im.projection_center() for i, im in r.images.items() if im.has_pose}
            shared = sorted(set(cur) & set(ref_c))
            src = np.array([cur[i] for i in shared])
            dst = np.array([ref_c[i] for i in shared])
            s, R, t = umeyama(src, dst)
            resid = np.linalg.norm((s * (R @ src.T).T + t) - dst, axis=1)
            print(f"[{lab}] gauge 对齐用 {len(shared)} 台相机  尺度 {s:.4f}  "
                  f"残差 中位 {np.median(resid):.4f} p90 {np.percentile(resid,90):.4f}", flush=True)
            xyz = s * (R @ xyz.T).T + t

        out = Path(f"ply_{lab}.ply")
        with open(out, "wb") as f:
            f.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\n"
                    "property float x\nproperty float y\nproperty float z\n"
                    "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                    "end_header\n".encode())
            rec = np.zeros(len(xyz), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                            ("r", "u1"), ("g", "u1"), ("b", "u1")])
            rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
            rec["r"], rec["g"], rec["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
            f.write(rec.tobytes())
        black = (rgb.sum(1) == 0).mean()
        print(f"[{lab}] 已写 {out}  {len(xyz):,} 点  全黑点占比 {black:.1%}", flush=True)

        # 把 ≥8 观测的点数补进 metrics.json,供并排页直接读取
        work = dict(ARMS)[lab]
        mp = Path(work) / "metrics.json"
        if mp.exists():
            import json
            m = json.loads(mp.read_text())
            tls = np.array([len(p.track.elements) for p in r.points3D.values()])
            m["ge8"] = int((tls >= 8).sum())
            m["ge15"] = int((tls >= 15).sum())
            mp.write_text(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
