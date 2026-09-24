#!/usr/bin/env python3
"""Per-image keypoint/descriptor statistics from a COLMAP database (read-only copy)."""
import sqlite3, sys, numpy as np, json

def load(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    imgs = dict(con.execute("select image_id,name from images").fetchall())
    kps = {}
    for iid, r, c, blob in con.execute("select image_id,rows,cols,data from keypoints"):
        if blob is None or r == 0:
            kps[iid] = np.zeros((0, 6), np.float32); continue
        a = np.frombuffer(blob, np.float32).reshape(r, c)
        if c == 2:
            a = np.hstack([a, np.tile([1, 0, 0, 1], (r, 1)).astype(np.float32)])
        elif c == 4:
            x, y, s, o = a.T
            a = np.stack([x, y, s*np.cos(o), -s*np.sin(o), s*np.sin(o), s*np.cos(o)], 1)
        kps[iid] = a
    descs = {}
    for iid, r, c, blob in con.execute("select image_id,rows,cols,data from descriptors"):
        descs[iid] = np.frombuffer(blob, np.uint8).reshape(r, c) if r else np.zeros((0, 128), np.uint8)
    tvg = con.execute("select pair_id,rows,config from two_view_geometries").fetchall()
    return con, imgs, kps, descs, tvg

def scale_orient(a):
    a11, a12, a21, a22 = a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    sx = np.sqrt(a11**2 + a21**2); sy = np.sqrt(a12**2 + a22**2)
    return 0.5*(sx+sy), np.arctan2(a21, a11)

def pair_ids(pid):
    MAX = 2147483647
    i2 = pid % MAX; i1 = (pid - i2) // MAX
    return int(i1), int(i2)

def stats(db, W=None, H=None):
    con, imgs, kps, descs, tvg = load(db)
    verified = {i: [] for i in imgs}
    for pid, rows, cfg in tvg:
        i1, i2 = pair_ids(pid)
        if rows and rows > 0:
            verified.setdefault(i1, []).append((i2, rows))
            verified.setdefault(i2, []).append((i1, rows))
    out = []
    for iid in sorted(imgs):
        a = kps.get(iid, np.zeros((0, 6)))
        d = descs.get(iid, np.zeros((0, 128), np.uint8))
        n = len(a)
        if n == 0:
            out.append(dict(image_id=iid, name=imgs[iid], n=0)); continue
        s, o = scale_orient(a)
        dn = np.linalg.norm(d.astype(np.float32), axis=1) if len(d) else np.array([0])
        rec = dict(image_id=iid, name=imgs[iid], n=int(n),
                   s_p10=float(np.percentile(s, 10)), s_med=float(np.median(s)), s_p90=float(np.percentile(s, 90)),
                   s_min=float(s.min()), s_max=float(s.max()),
                   frac_s_lt2=float((s < 2.0).mean()), frac_s_lt3=float((s < 3.0).mean()),
                   x_med=float(np.median(a[:, 0])), y_med=float(np.median(a[:, 1])),
                   x_rng=[float(a[:, 0].min()), float(a[:, 0].max())], y_rng=[float(a[:, 1].min()), float(a[:, 1].max())],
                   dnorm_med=float(np.median(dn)), dzero=int((d.sum(1) == 0).sum()) if len(d) else 0,
                   n_verified=len([v for v in verified.get(iid, []) if v[1] >= 15]),
                   inl_list=sorted([v[1] for v in verified.get(iid, [])], reverse=True)[:6],
                   aff_identity=float(np.mean((np.abs(a[:,3])<1e-9)&(np.abs(a[:,4])<1e-9)&(np.abs(a[:,2]-a[:,5])<1e-9))))
        out.append(rec)
    return out

if __name__ == "__main__":
    db = sys.argv[1]
    res = stats(db)
    if len(sys.argv) > 2 and sys.argv[2] == "--json":
        print(json.dumps(res)); sys.exit()
    for r in res:
        if r['n'] == 0:
            print(r['image_id'], r['name'], 'n=0'); continue
        print(f"{r['image_id']:4d} {r['name']:20s} n={r['n']:6d} scale p10/med/p90={r['s_p10']:.2f}/{r['s_med']:.2f}/{r['s_p90']:.2f} min={r['s_min']:.2f} <2:{r['frac_s_lt2']:.2f} <3:{r['frac_s_lt3']:.2f} x/y med={r['x_med']:.0f}/{r['y_med']:.0f} dnorm={r['dnorm_med']:.0f} dzero={r['dzero']} ver(>=15)={r['n_verified']} top={r['inl_list']} affI={r['aff_identity']:.2f}")
