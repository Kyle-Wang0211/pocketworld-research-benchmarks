#!/usr/bin/env python3
"""Archival renderer for stage0 cap41 device baseline (dependency-free).

Consumes the SAME views.json as cap41_device_baseline_viewer.html so both
renderers share one source of camera truth. Pure numpy + stdlib zlib PNG
writer; no matplotlib. Output PNGs are evidence snapshots; the interactive
HTML is the acceptance surface.

Usage: python3 render_views.py [ply_path] [out_dir]
Reuse for candidate clouds later: pass the candidate PLY, same views.json.
"""
import json, sys, os, zlib, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PLY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, "../../data/pocketworld_captures/cap41/device_2026-07-16/sfm_sparse.ply")
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
BG = np.array([16, 16, 20], dtype=np.uint8)

def load_ply(path):
    raw = open(path, "rb").read()
    hdr = raw[:2048].decode("latin1")
    n = int(hdr.split("element vertex ")[1].split("\n")[0])
    off = raw.index(b"end_header\n") + 11
    rec = np.frombuffer(raw[off:], dtype=np.dtype(
        [("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")]), count=n)
    xyz = np.stack([rec["x"],rec["y"],rec["z"]],1).astype(np.float64)
    rgb = np.stack([rec["r"],rec["g"],rec["b"]],1)
    return xyz, rgb

def write_png(path, img):
    h, w, _ = img.shape
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    rows = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)

def render(xyz, rgb, view, out_png, w=1600, h=1000, splat=1):
    eye = np.asarray(view["eye"]); target = np.asarray(view["target"])
    z = eye - target; z /= np.linalg.norm(z)
    x = np.cross([0,1,0], z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])
    pc = (xyz - eye) @ R.T
    zc = -pc[:,2]
    keep = zc > 1e-6
    pc, c, zc = pc[keep], rgb[keep], zc[keep]
    f = 1.0/np.tan(np.radians(view["fov"])/2)
    u = f*pc[:,0]/zc * (h/w); v = f*pc[:,1]/zc
    px = ((u+1)*0.5*w).astype(int); py = ((1-v)*0.5*h).astype(int)
    inside = (px>=0)&(px<w)&(py>=0)&(py<h)
    px, py, c, zc = px[inside], py[inside], c[inside], zc[inside]
    order = np.argsort(-zc)  # far first, near overwrites
    img = np.tile(BG, (h, w, 1))
    for dy in range(-splat, splat+1):
        for dx in range(-splat, splat+1):
            qx = np.clip(px[order]+dx, 0, w-1); qy = np.clip(py[order]+dy, 0, h-1)
            img[qy, qx] = c[order]
    write_png(out_png, img)

if __name__ == "__main__":
    views = json.load(open(os.path.join(HERE, "views.json")))
    xyz, rgb = load_ply(PLY)
    print(f"{len(xyz):,} pts from {PLY}")
    for name, v in views["views"].items():
        out = os.path.join(OUT, f"view_{name}.png")
        render(xyz, rgb, v, out)
        print("wrote", out)
