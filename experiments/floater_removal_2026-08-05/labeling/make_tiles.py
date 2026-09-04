#!/usr/bin/env python3
"""浮点真值盲标图块渲染(纯 numpy,无 matplotlib)。
每点一格:半径 0.4m 内邻居(灰)+ 候选(红十字),两正交视角(XZ 俯视 / XY 正视)。
判据 = 点是否落在局部表面/结构上。渲染时不含任何判据数值(盲标)。"""
import struct, sys, zlib
import numpy as np
from scipy.spatial import cKDTree

MODEL, OUT = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 300
START = int(sys.argv[4]) if len(sys.argv) > 4 else 0
SEED = 20260807
TILE, PAD, COLS = 150, 6, 6   # 每格 150px,一行 COLS 个候选(每候选 2 视角)

def read_pts(path):
    xyz = []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            struct.unpack("<Q", f.read(8))
            xyz.append(struct.unpack("<ddd", f.read(24))); f.read(3)
            struct.unpack("<d", f.read(8))
            tl = struct.unpack("<Q", f.read(8))[0]; f.read(tl * 8)
    return np.asarray(xyz)

def write_png(path, img):
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    open(path, "wb").write(png)

def draw_digit(img, x, y, ch, color=(60,60,60)):
    F = {  # 3x5 点阵
     '0':"111101101101111",'1':"010110010010111",'2':"111001111100111",
     '3':"111001111001111",'4':"101101111001001",'5':"111100111001111",
     '6':"111100111101111",'7':"111001001001001",'8':"111101111101111",
     '9':"111101111001111",'#':"101111101111101",' ':"000000000000000"}
    p = F.get(ch, F[' '])
    for r in range(5):
        for c in range(3):
            if p[r*3+c] == '1':
                img[y+r*2:y+r*2+2, x+c*2:x+c*2+2] = color

xyz = read_pts(f"{MODEL}/points3D.bin")
rng = np.random.default_rng(SEED)
idx = rng.choice(len(xyz), size=N, replace=False)
np.save(f"{OUT}/sample_idx.npy", idx)
tree = cKDTree(xyz); R = 0.40
PER = COLS * 4   # 每张 4 行

for sheet in range(START, (N + PER - 1) // PER):
    rows = 4
    W = COLS * (2 * TILE + PAD) + PAD
    H = rows * (TILE + 22) + PAD
    img = np.full((H, W, 3), 255, np.uint8)
    for k in range(PER):
        gi = sheet * PER + k
        if gi >= N: break
        i = idx[gi]; p = xyz[i]
        nb = tree.query_ball_point(p, R)
        loc = xyz[nb] - p
        r0, c0 = k // COLS, k % COLS
        oy = PAD + r0 * (TILE + 22) + 18
        for v, (a, b) in enumerate([(0, 2), (0, 1)]):
            ox = PAD + c0 * (2 * TILE + PAD) + v * TILE
            img[oy:oy+TILE, ox:ox+TILE] = 250
            img[oy:oy+TILE, ox] = 200; img[oy, ox:ox+TILE] = 200
            px = ((loc[:, a] / R * 0.5 + 0.5) * (TILE - 1)).astype(int)
            py = ((-loc[:, b] / R * 0.5 + 0.5) * (TILE - 1)).astype(int)
            ok = (px >= 0) & (px < TILE) & (py >= 0) & (py < TILE)
            img[oy + py[ok], ox + px[ok]] = (110, 110, 110)
            cx = cy = TILE // 2
            img[oy+cy-6:oy+cy+7, ox+cx] = (220, 20, 20)
            img[oy+cy, ox+cx-6:ox+cx+7] = (220, 20, 20)
        s = f"#{gi}"
        for j, ch in enumerate(s):
            draw_digit(img, PAD + c0*(2*TILE+PAD) + 2 + j*8, oy - 15, ch)
    write_png(f"{OUT}/sheet_{sheet:02d}.png", img)
    print("sheet", sheet, "-> ", f"{OUT}/sheet_{sheet:02d}.png")
