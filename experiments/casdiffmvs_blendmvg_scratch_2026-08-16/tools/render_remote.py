#!/usr/bin/env python3
"""在远端把全量点云渲成 PNG —— 让 1700 万个点全部参与渲染,只让图片过网。

⚠️ 为什么要这条路:本机到该实例实测只有约 110-190 KB/s,
   每份点云 250MB ⇒ 流式看要 25-40 分钟/份。而渲好的 PNG 只有几百 KB。
   **这不是降采样** —— 每一个点都进了 z-buffer,只是把渲染放在了数据那一侧。

纯 numpy z-buffer splat,不需要显示器/GL。
"""
import sys, json, os
import numpy as np

BIN = sys.argv[1]; OUT = sys.argv[2]
W, H = int(sys.argv[3]), int(sys.argv[4])
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(f"{BIN}/meta.json"))
tags = list(meta)

# 共享中心与尺度(取第一份)⇒ 四份构图完全一致,才能并排比
m0 = meta[tags[0]]
CEN = np.array(m0["center"], np.float32)
SCL = 2.0 / max(max(m0["ext"]), 1e-6)

# 若干机位:(绕Y角, 俯仰角, 距离)
VIEWS = [("v1_front", 0.6, -0.6, 2.5), ("v2_side", 2.0, -0.5, 2.5),
         ("v3_top", 0.6, -1.2, 2.6), ("v4_close", 1.2, -0.35, 1.3)]


def render(pos, col, ry, rx, dist):
    cy, sy = np.cos(ry), np.sin(ry); cr, sr = np.cos(rx), np.sin(rx)
    p = pos - CEN; p *= SCL
    x = cy * p[:, 0] - sy * p[:, 2]
    z0 = sy * p[:, 0] + cy * p[:, 2]
    y = cr * p[:, 1] + sr * z0
    z = -sr * p[:, 1] + cr * z0 + dist
    ok = z > 0.05
    f = 1.5
    u = (x[ok] * f / z[ok] * (H / 2) + W / 2)
    v = (-y[ok] * f / z[ok] * (H / 2) + H / 2)
    zz = z[ok]; cc = col[ok]
    ui = u.astype(np.int32); vi = v.astype(np.int32)
    inb = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
    ui, vi, zz, cc = ui[inb], vi[inb], zz[inb], cc[inb]
    # z-buffer:同像素取最近的点
    flat = vi.astype(np.int64) * W + ui
    order = np.argsort(-zz)                      # 远→近,近的后写覆盖远的
    img = np.zeros((H * W, 3), np.uint8)
    img[flat[order]] = cc[order]
    return img.reshape(H, W, 3)


from PIL import Image
for tag in tags:
    n = meta[tag]["n"]
    pos = np.fromfile(f"{BIN}/{tag}.pos", np.float32).reshape(n, 3)
    col = np.fromfile(f"{BIN}/{tag}.col", np.uint8).reshape(n, 3)
    for name, ry, rx, dist in VIEWS:
        img = render(pos, col, ry, rx, dist)
        Image.fromarray(img).save(f"{OUT}/{name}__{tag}.png", optimize=True)
    print(f"  {tag}: {n:,} 点 × {len(VIEWS)} 机位 ✓", flush=True)
    del pos, col
print(f"→ {OUT}")
