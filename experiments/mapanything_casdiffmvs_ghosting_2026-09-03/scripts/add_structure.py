#!/usr/bin/env python3
"""Append a `structure` array (landmarks + observations) to an AliceVision SfMData produced by the official
importMiddlebury, using the fused points and the per-point visibility we already computed. Streamed so a large
structure never has to exist as one Python string.

  add_structure.py <sfm_poses.sfm> <ws_dir> <out.sfm> [max_points]
"""
import sys, json, glob, numpy as np
SFM, WS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
MAXP = int(sys.argv[4]) if len(sys.argv) > 4 else 0
d = json.load(open(SFM))
views = {int(v["frameId"]) if "frameId" in v else i: v for i, v in enumerate(d["views"])}
# map our view index (0..131, = sorted filename order) -> AliceVision viewId, via the image basename
name2view = {v["path"].rsplit("/", 1)[-1]: v["viewId"] for v in d["views"]}
order = sorted(name2view)                       # 00000000.jpg ... == our view index order
vid_of = [name2view[n] for n in order]
K_of = {}; E_of = {}
for p in sorted(glob.glob(f"{WS}/../out_official/cams/*_cam.txt")):
    i = int(p.rsplit("/", 1)[-1][:8]); L = [l.rstrip() for l in open(p)]
    E_of[i] = np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4)
    K_of[i] = np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3)
P = np.load(f"{WS}/merged_xyz.npy"); C = np.load(f"{WS}/merged_rgb.npy")
b = open(f"{WS}/fused.ply.vis", "rb").read(); N = int(np.frombuffer(b[:8], "<u8")[0]); a = np.frombuffer(b[8:], "<u4")
starts = np.empty(N, np.int64); cnts = np.empty(N, np.int64); off = 0
for k in range(N): cnts[k] = a[off]; starts[k] = off + 1; off += 1 + cnts[k]
sel = np.arange(N) if (MAXP <= 0 or MAXP >= N) else np.linspace(0, N - 1, MAXP).astype(np.int64)
print(f"landmarks {len(sel)} of {N}; observations {int(cnts[sel].sum())}", flush=True)
head = json.dumps({k: d[k] for k in ("version", "views", "intrinsics", "poses")})[:-1]   # drop closing brace
with open(OUT, "w") as f:
    f.write(head); f.write(',"structure":[')
    for j, k in enumerate(sel):
        if j: f.write(",")
        ids = a[starts[k]:starts[k] + cnts[k]]
        X = P[k]; obs = []
        for v in ids:
            v = int(v); E = E_of[v]; K = K_of[v]
            Xc = E @ np.append(X, 1.0); z = Xc[2]
            if z <= 0: continue
            u = K[0, 0] * Xc[0] / z + K[0, 2]; vv = K[1, 1] * Xc[1] / z + K[1, 2]
            obs.append('{"observationId":"%s","featureId":"%d","x":["%.3f","%.3f"],"scale":"0"}' % (vid_of[v], j, u, vv))
        f.write('{"landmarkId":"%d","descType":"unknown","color":["%d","%d","%d"],"X":["%.6f","%.6f","%.6f"],"observations":[%s]}'
                % (j, C[k][0], C[k][1], C[k][2], X[0], X[1], X[2], ",".join(obs)))
        if j % 500000 == 0: print("  %d" % j, flush=True)
    f.write("]}")
import os; print("wrote", OUT, "%.2f GB" % (os.path.getsize(OUT) / 2**30), flush=True)
