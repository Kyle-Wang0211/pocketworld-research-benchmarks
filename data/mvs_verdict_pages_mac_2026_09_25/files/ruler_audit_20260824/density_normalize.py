#!/usr/bin/env python3
"""密度归一 —— 把五臂随机降采样到同一点数(以 dtu 的 2,329,310 为准),固定随机种子。

⚠️ 已知教训(handoff §5③):纯降采样只删点不移点,任何"精度改善"都是幸存者效应。
   这里只用于判尺子(同保留率下重跑尺子看排名是否塌陷),绝不用于判权重好坏。

写出的新 PLY 与原脚本 load() 读取的二进制格式(binary_little_endian,
x,y,z float32 + r,g,b uchar)逐字节一致,可直接喂给 cloud_vs_ref.py /
wall_flatness.py / ghost_mass.py(用 --sub 1,因为已经降采样过一次了)。
"""
import numpy as np
import sys, os

DT = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
               ("r", "u1"), ("g", "u1"), ("b", "u1")])

TARGET = 2_329_310
SEED = 20260824

SRC_DIR = "~/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
OUT_DIR = os.path.join(SRC_DIR, "ruler_audit_20260824", "density_norm")
os.makedirs(OUT_DIR, exist_ok=True)

ARMS = [
    ("dtu", "dense_dtu.ply"),
    ("blend", "dense_blend.ply"),
    ("blendmvg", "dense_blendmvg.ply"),
    ("C", "dense_Cours.ply"),
    ("新权重", "dense_mvgZeroDTU.ply"),
]


def load_full(p):
    f = open(p, "rb")
    n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"):
            n = int(l.split()[-1])
        if l.strip() == b"end_header":
            break
    rec = np.fromfile(f, dtype=DT, count=n)
    return rec


def write_ply(path, rec):
    n = len(rec)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    with open(path, "wb") as f:
        f.write(header)
        rec.tofile(f)


def main():
    rng = np.random.default_rng(SEED)  # 同一个生成器按固定臂序依次消耗 -> 全过程可复现
    print(f"目标点数 {TARGET:,} · 种子 {SEED}\n")
    for lab, fn in ARMS:
        src = os.path.join(SRC_DIR, fn)
        rec = load_full(src)
        n_full = len(rec)
        if n_full < TARGET:
            print(f"  !! {lab}: 全量点数 {n_full:,} < 目标 {TARGET:,},跳过")
            continue
        idx = rng.choice(n_full, TARGET, replace=False)
        idx.sort()  # 保持磁盘局部性,不影响随机性(选择已经是均匀随机的)
        sub = rec[idx]
        out = os.path.join(OUT_DIR, f"dnorm_{lab.replace('新权重','mvgZeroDTU')}.ply")
        write_ply(out, sub)
        print(f"  {lab:<10} 全量 {n_full:>11,} -> 降采样 {len(sub):>11,}  写入 {out}")
        del rec, sub, idx


if __name__ == "__main__":
    main()
