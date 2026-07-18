#!/usr/bin/env python3.11
"""E16 diagnostic: distribution of ORB-SLAM baseline/medianSceneDepth ratio
over the ACTUAL temporal pair set (gap <= 12) of the banked E9 off runs.
Answers: at what threshold would M2 start biting on cap50/cap51?"""
import struct, sys
import numpy as np

def read_images_bin(path):
    """COLMAP images.bin -> {image_id: (R(3x3), t(3,), [point3D_ids])}"""
    out = {}
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            (iid,) = struct.unpack("<I", f.read(4))
            q = struct.unpack("<4d", f.read(32))
            t = np.array(struct.unpack("<3d", f.read(24)))
            (cam_id,) = struct.unpack("<I", f.read(4))
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00": break
                name += c
            (np2,) = struct.unpack("<Q", f.read(8))
            pts = np.frombuffer(f.read(24 * np2), dtype="<f8").reshape(np2, 3)
            xy = pts[:, :2]
            p3 = np.frombuffer(np.ascontiguousarray(pts[:, 2]).tobytes(), dtype="<i8")
            w, x, y, z = q
            R = np.array([
                [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
            out[iid] = (R, t, p3[p3 >= 0], name.decode())
    return out

def read_points3d_bin(path):
    xyz = {}
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            (pid,) = struct.unpack("<Q", f.read(8))
            p = np.array(struct.unpack("<3d", f.read(24)))
            f.read(3 + 8)
            (tl,) = struct.unpack("<Q", f.read(8))
            f.read(8 * tl)
            xyz[pid] = p
    return xyz

def main(run_dir, k=12):
    imgs = read_images_bin(f"{run_dir}/images.bin")
    pts = read_points3d_bin(f"{run_dir}/points3D.bin")
    ids = sorted(imgs)  # image_id = frame_id+1 ordering (temporal)
    ratios, details = [], []
    for a_i, iid1 in enumerate(ids):
        for iid2 in ids[a_i+1:]:
            if iid2 - iid1 > k: break
            R1, t1, p31, _ = imgs[iid1]
            R2, t2, p32, _ = imgs[iid2]
            C1, C2 = -R1.T @ t1, -R2.T @ t2
            base = np.linalg.norm(C1 - C2)
            # ORB-SLAM ComputeSceneMedianDepth on the EARLIER frame (prev):
            obs = p31
            if len(obs) == 0: continue
            P = np.array([pts[p] for p in obs if p in pts])
            if len(P) == 0: continue
            depth = (R1 @ P.T).T[:, 2] + t1[2]
            depth = depth[depth > 0]
            if len(depth) == 0: continue
            med = np.sort(depth)[(len(depth)-1)//2]
            ratios.append(base / med)
            details.append((iid1, iid2, base, med))
    r = np.array(ratios)
    print(f"{run_dir.split('/')[-1]}: n_pairs={len(r)}")
    print(f"  ratio min={r.min():.4f} p1={np.percentile(r,1):.4f} p5={np.percentile(r,5):.4f} "
          f"p10={np.percentile(r,10):.4f} p25={np.percentile(r,25):.4f} p50={np.percentile(r,50):.4f} p90={np.percentile(r,90):.4f}")
    for thr in (0.005, 0.01, 0.02, 0.035, 0.05, 0.08, 0.10, 0.15):
        print(f"  banned@{thr}: {(r<thr).sum()} pairs ({100*(r<thr).mean():.1f}%)")
    # adjacent-frame-only view (gap=1, smallest baselines)
    g1 = np.array([b/m for (i1,i2,b,m) in details if i2-i1 == 1])
    if len(g1):
        print(f"  gap=1 pairs: n={len(g1)} min={g1.min():.4f} p50={np.median(g1):.4f}")
    b = np.array([d[2] for d in details]); m = np.array([d[3] for d in details])
    print(f"  baseline_m: min={b.min():.3f} p50={np.median(b):.3f}  meddepth_m: p50={np.median(m):.3f}")

if __name__ == "__main__":
    for rd in sys.argv[1:]:
        main(rd)
