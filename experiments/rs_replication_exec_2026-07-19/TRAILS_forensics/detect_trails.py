#!/usr/bin/env python3.11
"""
E2-A trail forensics, stage 2: detector + statistics + visualization products.

Trail candidate = union of three constructive signatures (per README honesty notes):

  S_behind : the segment primary-camera -> point crosses dense existing structure
             (voxel occupancy ray-march). A real surface point is seen directly; a
             specular/mirror virtual point lives BEHIND a real surface => impossible.
  S_below  : floor_h < -0.10 m (below the production-arbitrated floor plane, deeper
             than the known 2-3.5cm double-floor band => physically impossible).
  S_streak : sparse wisp (local 10cm count <= 10) belonging to a radius-15cm connected
             string of >=4 pts whose PCA major axis is elongated (>=3.0) AND aligned
             with the member mean viewing ray (|cos|>=0.80) => smeared along sight line.
  S_out    : detached wisp beyond the dense scene shell (task signature 2, data-driven:
             core = pts with >=40 neighbors in 10cm; candidate has cnt10<=10 AND
             distance to nearest core point > 0.25 m) => outside real scene geometry.

Candidates are then clustered (20cm connected components); every cluster gets a full
fingerprint row (size, extent, elongation, axis-ray angle, tri-angle, resid, track).
Products: highlight PLY (trail=red, rest true color), trails-only true-color PLY,
top/elevation PNGs, fingerprint histograms trail-vs-clean, stats.json.
"""
import numpy as np, json, os, sys, hashlib
from collections import defaultdict
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
OUT_BASE = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_forensics"

VOX = 0.05                 # occupancy voxel size (m)
VOX_SOLID = 6              # points in a voxel => solid evidence
MARCH_STEP = 0.04          # ray-march step (m)
MARCH_START = 0.25         # skip near camera (m)
MARCH_STOP = 0.20          # stop short of the point (m) - don't count its own surface
BLOCK_MIN_HITS = 3         # solid samples crossed => behind-surface
DENS_R = 0.10              # local density radius
WISP_MAX_CNT = 10          # sparse-wisp gate
STREAK_LINK = 0.15         # streak connected-component linking radius
STREAK_MIN = 4             # min string size
STREAK_ELONG = 3.0
STREAK_ALIGN = 0.80        # |cos| axis vs mean ray
BELOW_FLOOR = -0.10        # m
CORE_CNT = 40              # cnt10 >= this => dense-shell core point
OUT_DIST = 0.25            # m beyond core => detached
OUT_MAX_CNT = 10
CLUSTER_LINK = 0.20        # final candidate clustering radius
MIN_CLUSTER = 3            # clusters below this reported as 'isolated' (kept in point list)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""): h.update(ch)
    return h.hexdigest()

def write_ply(path, xyz, rgb, comment):
    n = len(xyz)
    with open(path, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"comment {comment}\n".encode())
        f.write(f"element vertex {n}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        rec = np.empty(n, dtype=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")]))
        rec["x"], rec["y"], rec["z"] = xyz[:,0].astype("<f4"), xyz[:,1].astype("<f4"), xyz[:,2].astype("<f4")
        rec["r"], rec["g"], rec["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
        rec.tofile(f)

def connected_components(pts, radius):
    if len(pts) == 0: return np.zeros(0, int)
    tree = cKDTree(pts)
    pairs = tree.query_pairs(radius, output_type="ndarray")
    parent = np.arange(len(pts))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    return np.array([find(i) for i in range(len(pts))])

def run_cap(cap):
    out = os.path.join(OUT_BASE, cap)
    d = np.load(os.path.join(out, "fingerprints.npz"))
    xyz, rgb = d["xyz"], d["rgb"]
    ray, floor_h = d["ray"], d["floor_h"]
    n_support, tri_angle = d["n_support"], d["tri_angle"]
    mean_resid, max_resid = d["mean_resid"], d["max_resid"]
    cam_depth, prim_fid = d["cam_depth"], d["prim_fid"]
    camC, cam_fids = d["camC"], d["cam_fids"]
    ray_proxy = d["ray_proxy"]
    nP = len(xyz)
    fid2C = {int(f): camC[i] for i, f in enumerate(cam_fids)}
    print(f"=== {cap} n={nP} ===", flush=True)

    # local density
    tree = cKDTree(xyz)
    cnt10 = tree.query_ball_point(xyz, DENS_R, return_length=True, workers=-1)

    # voxel occupancy
    key = np.floor(xyz / VOX).astype(np.int64)
    vox = defaultdict(int)
    for k in map(tuple, key): vox[k] += 1
    solid = {k for k, v in vox.items() if v >= VOX_SOLID}
    print(f"solid voxels {len(solid)} / {len(vox)}", flush=True)

    # S_behind: ray-march camera->point through solid voxels (suspects = sparse-ish points)
    suspects = np.flatnonzero((cnt10 <= 40) & (cam_depth > 0.8))
    behind_hits = np.zeros(nP, np.int16)
    own_vox = [tuple(k) for k in key]
    for pi in suspects:
        C = fid2C.get(int(prim_fid[pi]))
        if C is None: continue
        X = xyz[pi]; v = X - C; L = np.linalg.norm(v)
        if L <= MARCH_START + MARCH_STOP + 0.1: continue
        u = v / L
        ts = np.arange(MARCH_START, L - MARCH_STOP, MARCH_STEP)
        sk = np.floor((C[None, :] + ts[:, None] * u[None, :]) / VOX).astype(np.int64)
        hits = 0; prev = None
        for k in map(tuple, sk):
            if k == prev: continue
            prev = k
            if k in solid and k != own_vox[pi]: hits += 1
        behind_hits[pi] = hits
    S_behind = behind_hits >= BLOCK_MIN_HITS
    print(f"S_behind {int(S_behind.sum())} (suspects {len(suspects)})", flush=True)

    # S_below
    S_below = floor_h < BELOW_FLOOR
    print(f"S_below {int(S_below.sum())}", flush=True)

    # S_streak: sparse wisps forming sight-line strings
    wisp = np.flatnonzero(cnt10 <= WISP_MAX_CNT)
    S_streak = np.zeros(nP, bool)
    streak_info = []
    if len(wisp):
        lab = connected_components(xyz[wisp], STREAK_LINK)
        for lb in np.unique(lab):
            mem = wisp[lab == lb]
            if len(mem) < STREAK_MIN: continue
            P = xyz[mem]
            mu = P.mean(0)
            ev, evec = np.linalg.eigh(np.cov((P - mu).T))
            elong_c = float(np.sqrt(max(ev[2], 0) / max(ev[1], 1e-12)))
            axis = evec[:, 2]
            mray = ray[mem].mean(0); mray /= (np.linalg.norm(mray) + 1e-15)
            align_c = float(abs(axis @ mray))
            length = float(np.sqrt(max(ev[2], 0)) * 2)
            if elong_c >= STREAK_ELONG and align_c >= STREAK_ALIGN:
                S_streak[mem] = True
                streak_info.append({"n": int(len(mem)), "elong": round(elong_c, 2),
                                    "align": round(align_c, 3), "len_m": round(length, 2)})
    print(f"S_streak {int(S_streak.sum())} in {len(streak_info)} strings", flush=True)

    # S_out: detached beyond dense shell
    core = cnt10 >= CORE_CNT
    ct = cKDTree(xyz[core])
    dist_core, _ = ct.query(xyz, workers=-1)
    S_out = (dist_core > OUT_DIST) & (cnt10 <= OUT_MAX_CNT)
    print(f"S_out {int(S_out.sum())}", flush=True)

    cand = S_behind | S_below | S_streak | S_out
    ci = np.flatnonzero(cand)
    print(f"TRAIL CANDIDATES {len(ci)} ({100*len(ci)/nP:.2f}%)", flush=True)

    # final clustering + per-cluster fingerprints
    clusters = []
    if len(ci):
        lab = connected_components(xyz[ci], CLUSTER_LINK)
        for lb in np.unique(lab):
            mem = ci[lab == lb]
            P = xyz[mem]
            mu = P.mean(0)
            if len(mem) >= 3:
                ev, evec = np.linalg.eigh(np.cov((P - mu).T))
                elong_c = float(np.sqrt(max(ev[2], 0) / max(ev[1], 1e-12)))
                axis = evec[:, 2]
                mray = ray[mem].mean(0); mray /= (np.linalg.norm(mray) + 1e-15)
                ang = float(np.degrees(np.arccos(np.clip(abs(axis @ mray), 0, 1))))
                length = float(np.sqrt(max(ev[2], 0)) * 2)
            else:
                elong_c, ang, length = None, None, None
            ta = tri_angle[mem]; mres = max_resid[mem]
            clusters.append({
                "id": int(lb), "n": int(len(mem)),
                "centroid": [round(float(x), 3) for x in mu],
                "len_m": None if length is None else round(length, 2),
                "elong": None if elong_c is None else round(elong_c, 2),
                "axis_ray_angle_deg": None if ang is None else round(ang, 1),
                "sig": {"behind": int(S_behind[mem].sum()), "below": int(S_below[mem].sum()),
                        "streak": int(S_streak[mem].sum()), "out": int(S_out[mem].sum())},
                "n_support_med": float(np.median(n_support[mem])),
                "frac_no_obs": round(float((n_support[mem] == 0).mean()), 3),
                "tri_angle_med": None if not np.isfinite(ta).any() else round(float(np.nanmedian(ta)), 2),
                "max_resid_med": None if not np.isfinite(mres).any() else round(float(np.nanmedian(mres)), 2),
                "cam_depth_med": round(float(np.median(cam_depth[mem])), 2),
                "floor_h_med": round(float(np.median(floor_h[mem])), 2),
                "cnt10_med": float(np.median(cnt10[mem])),
                "member_idx_sample": [int(x) for x in mem[:20]],
            })
        clusters.sort(key=lambda c: -c["n"])
        for rank, c in enumerate(clusters): c["rank"] = rank
    big = [c for c in clusters if c["n"] >= MIN_CLUSTER]

    # ---- products ----
    hi_rgb = rgb.copy(); hi_rgb[cand] = (255, 0, 0)
    p1 = os.path.join(out, f"trail_highlight_{cap}.ply")
    write_ply(p1, xyz, hi_rgb, f"E2-A {cap}: trail candidates red (S_behind|S_below|S_streak), rest production true color; production gauge, no Sim3")
    p2 = os.path.join(out, f"trails_only_{cap}.ply")
    write_ply(p2, xyz[cand], rgb[cand], f"E2-A {cap}: trail candidate points only, production true color")

    # renders
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    for ax, (a, b, la, lb_, inv) in zip(axes, [(0, 2, "X", "Z", False), (2, 1, "Z", "Y", True)]):
        ax.scatter(xyz[~cand][:, a], xyz[~cand][:, b], s=0.25, c=rgb[~cand]/255.0, linewidths=0)
        ax.scatter(xyz[cand][:, a], xyz[cand][:, b], s=2.5, c="red", linewidths=0)
        ax.scatter(camC[:, a], camC[:, b], s=16, c="magenta", marker="^")
        ax.set_xlabel(la); ax.set_ylabel(lb_); ax.set_aspect("equal")
        if inv: ax.invert_yaxis()
        ax.set_title(f"{cap} {'topview' if not inv else 'elevation'} - trail candidates red ({len(ci)} pts)")
        ax.set_facecolor("#202020")
    plt.tight_layout(); plt.savefig(os.path.join(out, f"trails_topview_elev_{cap}.png"), dpi=110); plt.close()

    # fingerprint distributions trail vs clean
    clean = ~cand
    fig, axes = plt.subplots(1, 4, figsize=(22, 4.5))
    specs = [
        (np.log10(np.maximum(cnt10, 1)), "log10 local cnt (10cm)", None),
        (tri_angle, "tri-angle deg (n_support>=2)", (0, 40)),
        (n_support, "n recoverable support frames", (0, 8)),
        (floor_h, "height above floor plane (m)", (-0.5, 3)),
    ]
    for ax, (arr, ttl, rng) in zip(axes, specs):
        for m, col, lbl in ((clean, "#4477aa", "clean"), (cand, "red", "trail")):
            a = np.asarray(arr, float)[m]; a = a[np.isfinite(a)]
            if len(a) == 0: continue
            ax.hist(a, bins=40, range=rng, density=True, alpha=0.55, color=col, label=f"{lbl} (n={len(a)})")
        ax.set_title(ttl); ax.legend()
    plt.suptitle(f"{cap} fingerprints: trail candidates vs clean")
    plt.tight_layout(); plt.savefig(os.path.join(out, f"fingerprint_dists_{cap}.png"), dpi=110); plt.close()

    np.save(os.path.join(out, "trail_mask.npy"), cand)
    np.savez_compressed(os.path.join(out, "trail_detect.npz"),
                        cand=cand, S_behind=S_behind, S_below=S_below, S_streak=S_streak,
                        S_out=S_out, dist_core=dist_core, behind_hits=behind_hits, cnt10=cnt10)
    stats = {
        "cap": cap, "n_points": nP,
        "detector": {
            "S_behind": {"n": int(S_behind.sum()), "rule": f"ray-march {VOX}m voxels(>= {VOX_SOLID} pts=solid), >= {BLOCK_MIN_HITS} solid crossings, stop {MARCH_STOP}m short"},
            "S_below": {"n": int(S_below.sum()), "rule": f"floor_h < {BELOW_FLOOR} (production floor plane, below double-floor band)"},
            "S_streak": {"n": int(S_streak.sum()), "n_strings": len(streak_info),
                          "rule": f"cnt10<={WISP_MAX_CNT}, link {STREAK_LINK}m, n>={STREAK_MIN}, elong>={STREAK_ELONG}, |cos(axis,ray)|>={STREAK_ALIGN}"},
            "S_out": {"n": int(S_out.sum()), "rule": f"cnt10<={OUT_MAX_CNT} AND dist-to-core(cnt10>={CORE_CNT}) > {OUT_DIST}m (data-driven scene shell)"},
            "union": int(cand.sum()), "union_pct": round(100.0 * cand.sum() / nP, 3),
            "overlap": {"behind&below": int((S_behind & S_below).sum()),
                         "behind&streak": int((S_behind & S_streak).sum()),
                         "below&streak": int((S_below & S_streak).sum()),
                         "out&streak": int((S_out & S_streak).sum()),
                         "out&behind": int((S_out & S_behind).sum())},
        },
        "fingerprint_contrast": {
            "cnt10_med": {"trail": float(np.median(cnt10[cand])) if cand.any() else None, "clean": float(np.median(cnt10[clean]))},
            "no_obs_frac": {"trail": round(float((n_support[cand] == 0).mean()), 3) if cand.any() else None,
                             "clean": round(float((n_support[clean] == 0).mean()), 3)},
            "tri_angle_med": {"trail": round(float(np.nanmedian(tri_angle[cand])), 2) if np.isfinite(tri_angle[cand]).any() else None,
                               "clean": round(float(np.nanmedian(tri_angle[clean])), 2)},
            "cam_depth_med": {"trail": round(float(np.median(cam_depth[cand])), 2) if cand.any() else None,
                               "clean": round(float(np.median(cam_depth[clean])), 2)},
        },
        "clusters_ge3": big[:40],
        "n_clusters_total": len(clusters),
        "n_isolated_lt3": int(sum(c["n"] for c in clusters if c["n"] < MIN_CLUSTER)),
        "outputs": {os.path.basename(p): sha256(p) for p in [p1, p2]},
        "honesty": [
            "detector will have false positives: sparse REAL geometry seen through a real door opening satisfies S_streak-like sparsity; audit crops quantify this",
            "S_behind depends on primary-camera choice; points with 0 recoverable obs use nearest camera (proxy) - direction may be wrong for them",
            "ghost per-point mask bits not used (order mismatch 93,360 vs 92,849)",
        ],
    }
    json.dump(stats, open(os.path.join(out, "trail_stats.json"), "w"), indent=2)
    print(json.dumps(stats["detector"], indent=1), flush=True)
    return stats

if __name__ == "__main__":
    for cap in (sys.argv[1:] or ["cap50", "cap51"]):
        run_cap(cap)
    print("DONE", flush=True)
