#!/usr/bin/env python3.11
"""E13 shared parsing library — COLMAP bin models + sfm_live.db keypoints.

Read-only on all inputs; used by recon/inventory/settlement scripts.
"""
import os
import sqlite3
import struct

import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E9_RUNS = f"{EXP}/E9_birth_alias/runs"
E13 = f"{EXP}/E13_dual_birth_inventory"

# Task-designated off baselines (E9 banked runs, full tracks in points3D.bin).
OFF_RUN = {"cap50": f"{E9_RUNS}/cap50_off_r2", "cap51": f"{E9_RUNS}/cap51_off_r2"}
DB_PATH = {c: f"{D}/data/pocketworld_captures/{c}/device_full_pull_2026-07-17/sfm_live.db" for c in ("cap50", "cap51")}
GHOST_MASK = {c: f"{D}/data/pocketworld_captures/{c}/device_full_pull_2026-07-17/ghost_mask.json" for c in ("cap50", "cap51")}
DEVICE_PLY = {c: f"{D}/data/pocketworld_captures/{c}/device_full_pull_2026-07-17/sfm_sparse.ply" for c in ("cap50", "cap51")}
PHOTOS = {c: f"{D}/data/pocketworld_captures/{c}/device_full_pull_2026-07-17/photos_highres" for c in ("cap50", "cap51")}


def read_points3d_bin_full(path):
    """Full parse: ids, xyz, rgb, error, tracks [(image_id, point2D_idx)...]."""
    with open(path, "rb") as f:
        buf = f.read()
    n = struct.unpack_from("<Q", buf, 0)[0]
    off = 8
    ids = np.empty(n, np.int64)
    xyz = np.empty((n, 3), np.float64)
    rgb = np.empty((n, 3), np.uint8)
    err = np.empty(n, np.float64)
    tracks = []
    for i in range(n):
        pid = struct.unpack_from("<Q", buf, off)[0]
        off += 8
        xyz[i] = struct.unpack_from("<3d", buf, off)
        off += 24
        rgb[i] = struct.unpack_from("<3B", buf, off)
        off += 3
        err[i] = struct.unpack_from("<d", buf, off)[0]
        off += 8
        tl = struct.unpack_from("<Q", buf, off)[0]
        off += 8
        tr = np.frombuffer(buf, dtype="<u4", count=2 * tl, offset=off).reshape(tl, 2).copy()
        off += 8 * tl
        ids[i] = pid
        tracks.append(tr)
    assert off == len(buf), f"points3D.bin trailing bytes: {len(buf)-off}"
    return ids, xyz, rgb, err, tracks


def read_images_bin_full(path):
    """Full parse: per image -> dict(qvec,tvec,camera_id,name,xys,p3d_ids)."""
    with open(path, "rb") as f:
        buf = f.read()
    n = struct.unpack_from("<Q", buf, 0)[0]
    off = 8
    images = {}
    for _ in range(n):
        image_id = struct.unpack_from("<I", buf, off)[0]
        off += 4
        qvec = np.array(struct.unpack_from("<4d", buf, off))
        off += 32
        tvec = np.array(struct.unpack_from("<3d", buf, off))
        off += 24
        camera_id = struct.unpack_from("<I", buf, off)[0]
        off += 4
        end = buf.index(b"\x00", off)
        name = buf[off:end].decode()
        off = end + 1
        np2 = struct.unpack_from("<Q", buf, off)[0]
        off += 8
        rec = np.frombuffer(buf, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("p3d", "<i8")]), count=np2, offset=off)
        off += 24 * np2
        images[image_id] = {
            "qvec": qvec, "tvec": tvec, "camera_id": camera_id, "name": name,
            "xys": np.stack([rec["x"], rec["y"]], 1).copy(), "p3d_ids": rec["p3d"].copy(),
        }
    assert off == len(buf), f"images.bin trailing bytes: {len(buf)-off}"
    return images


def read_cameras_bin(path):
    with open(path, "rb") as f:
        buf = f.read()
    n = struct.unpack_from("<Q", buf, 0)[0]
    off = 8
    cams = {}
    NPARAMS = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}
    for _ in range(n):
        cid, model = struct.unpack_from("<Ii", buf, off)
        off += 8
        w, h = struct.unpack_from("<QQ", buf, off)
        off += 16
        npar = NPARAMS[model]
        params = np.array(struct.unpack_from(f"<{npar}d", buf, off))
        off += 8 * npar
        cams[cid] = {"model_id": model, "width": w, "height": h, "params": params}
    assert off == len(buf), f"cameras.bin trailing bytes: {len(buf)-off}"
    return cams


def qvec2rot(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def load_db_keypoints(db_path):
    """image_id -> float32 (N,2) xy from sfm_live.db keypoints table (first 2 of 6 cols)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = {}
    for image_id, rows, cols, blob in con.execute("SELECT image_id, rows, cols, data FROM keypoints"):
        a = np.frombuffer(blob, dtype="<f4").reshape(rows, cols)
        out[image_id] = a[:, :2].copy()
    con.close()
    return out


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
        d = np.fromfile(f, dtype=rec, count=n)
    return np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64), np.stack([d["r"], d["g"], d["b"]], 1)


def write_ply(path, xyz, rgb):
    rec = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    d = np.empty(len(xyz), rec)
    d["x"], d["y"], d["z"] = xyz[:, 0].astype(np.float32), xyz[:, 1].astype(np.float32), xyz[:, 2].astype(np.float32)
    d["r"], d["g"], d["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\n"
                 "property float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
        d.tofile(f)


def load_plane(cap):
    import json
    gm = json.load(open(GHOST_MASK[cap]))
    return np.array(gm["plane_n"], float), float(gm["plane_d"])


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
