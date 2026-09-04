#!/usr/bin/env python3
"""Birth-gate A/B (tri_min_angle 1.5/current -> 3 deg at stage-1) two-arm table.

Metric definitions copied from analyze_metadata_filter.py (same repo dir):
shell = 1.3-2.0 m radius band from centroid, core = r < 1.3, far = r > 2.0.
The BASELINE arm's centroid is used for BOTH arms (same ARKit-anchored gauge)
so band membership is directly comparable.

Delivered = production deliver-layer filter (max pairwise tri angle >= 3 deg,
OFFICIAL_AETHER_DELIVER_MIN_TRI_ANGLE default) applied on the full bin model —
the same python口径 the 3° threshold was calibrated with; cloud.ply vertex
count is printed as the C++-side cross-check.
"""
import struct
import sys

import numpy as np

BASE = sys.argv[1] if len(sys.argv) > 1 else "arm_base"
TEST = sys.argv[2] if len(sys.argv) > 2 else "arm_3deg"


def read_images_bin(path):
    centres = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            image_id = struct.unpack("<I", f.read(4))[0]
            qw, qx, qy, qz = struct.unpack("<dddd", f.read(32))
            tx, ty, tz = struct.unpack("<ddd", f.read(24))
            struct.unpack("<I", f.read(4))
            while f.read(1) != b"\x00":
                pass
            npts = struct.unpack("<Q", f.read(8))[0]
            f.seek(npts * 24, 1)
            q = np.array([qw, qx, qy, qz])
            q = q / np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ])
            centres[image_id] = -R.T @ np.array([tx, ty, tz])
    return centres


def read_points3d_bin(path):
    xyz, err, tracks = [], [], []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            struct.unpack("<Q", f.read(8))
            x, y, z = struct.unpack("<ddd", f.read(24))
            f.read(3)
            e = struct.unpack("<d", f.read(8))[0]
            tlen = struct.unpack("<Q", f.read(8))[0]
            t = np.frombuffer(f.read(tlen * 8), dtype="<u4").reshape(tlen, 2)
            xyz.append((x, y, z))
            err.append(e)
            tracks.append(t[:, 0].copy())
    return np.asarray(xyz), np.asarray(err), tracks


def ply_vertex_count(path):
    try:
        with open(path, "rb") as f:
            head = f.read(512).decode("latin1")
        for line in head.splitlines():
            if line.startswith("element vertex"):
                return int(line.split()[-1])
    except OSError:
        pass
    return -1


def load(model):
    centres = read_images_bin(f"{model}/images.bin")
    xyz, err, tracks = read_points3d_bin(f"{model}/points3D.bin")
    n = len(xyz)
    ang = np.empty(n)
    for i in range(n):
        cs = np.array([centres[iid] for iid in tracks[i] if iid in centres])
        if len(cs) >= 2:
            v = cs - xyz[i]
            v = v / np.linalg.norm(v, axis=1, keepdims=True)
            dot = v @ v.T
            np.fill_diagonal(dot, 1.0)
            ang[i] = np.degrees(np.arccos(np.clip(dot.min(), -1.0, 1.0)))
        else:
            ang[i] = 0.0
    tlen = np.array([len(t) for t in tracks])
    return dict(centres=centres, xyz=xyz, err=err, ang=ang, tlen=tlen,
                ply=ply_vertex_count(f"{model}/cloud.ply"))


def stats(d, centroid):
    xyz, err, ang, tlen = d["xyz"], d["err"], d["ang"], d["tlen"]
    r = np.linalg.norm(xyz - centroid, axis=1)
    shell = (r >= 1.3) & (r <= 2.0)
    core = r < 1.3
    far = r > 2.0
    deliver = ang >= 3.0
    out = dict(
        n_images=len(d["centres"]),
        n_points=len(xyz),
        n_deliver=int(deliver.sum()),
        ply=d["ply"],
        core=int(core.sum()), shell=int(shell.sum()), far=int(far.sum()),
        core_deliver=int((core & deliver).sum()),
        shell_deliver=int((shell & deliver).sum()),
        far_deliver=int((far & deliver).sum()),
        err_p50=float(np.percentile(err, 50)),
        err_p90=float(np.percentile(err, 90)),
        ang_p50=float(np.percentile(ang, 50)),
        ang_p10=float(np.percentile(ang, 10)),
        tlen_p50=float(np.percentile(tlen, 50)),
        two_view_pct=float(100 * (tlen == 2).mean()),
    )
    return out


a = load(BASE)
b = load(TEST)
centroid = a["xyz"].mean(axis=0)
sa = stats(a, centroid)
sb = stats(b, centroid)

rows = [
    ("registered images", "n_images", "d"),
    ("total model points", "n_points", "d"),
    ("delivered (ang>=3, py)", "n_deliver", "d"),
    ("delivered (cloud.ply, C++)", "ply", "d"),
    ("core pts (r<1.3, model)", "core", "d"),
    ("shell pts (1.3-2.0, model)", "shell", "d"),
    ("far pts (>2.0, model)", "far", "d"),
    ("core pts (delivered)", "core_deliver", "d"),
    ("shell pts (delivered)", "shell_deliver", "d"),
    ("far pts (delivered)", "far_deliver", "d"),
    ("error p50 (px)", "err_p50", "f"),
    ("error p90 (px)", "err_p90", "f"),
    ("tri angle p10 (deg)", "ang_p10", "f"),
    ("tri angle p50 (deg)", "ang_p50", "f"),
    ("track len p50", "tlen_p50", "f"),
    ("2-view share (%)", "two_view_pct", "f"),
]
print(f"{'metric':>28} | {'baseline':>10} | {'3deg arm':>10} | {'delta':>10}")
print("-" * 68)
for label, key, fmt in rows:
    va, vb = sa[key], sb[key]
    if fmt == "d":
        delta = vb - va
        pct = f" ({100.0 * delta / va:+.1f}%)" if va else ""
        print(f"{label:>28} | {va:>10d} | {vb:>10d} | {delta:>+6d}{pct}")
    else:
        print(f"{label:>28} | {va:>10.3f} | {vb:>10.3f} | {vb - va:>+10.3f}")
