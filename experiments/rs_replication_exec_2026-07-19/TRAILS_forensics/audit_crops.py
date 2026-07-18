#!/usr/bin/env python3.11
"""
E2-A trail forensics, stage 3: false-positive audit crops.

For each top trail cluster (and a random sample of isolated candidates), project the
member points into a real capture photo (refined production pose, frozen K, photo is
native 3840x2160 == db camera size) and save an annotated crop. A human then judges:
does the image region look like mirror/glass/specular content (true trail) or real
geometry (detector false positive)?

Frame selection per cluster: the member-supported primary frame (mode); if none, the
camera nearest to the cluster centroid that sees it in-image. Points BEHIND the camera
or out of image are skipped (counted).
"""
import numpy as np, json, os, sys
from collections import Counter
from PIL import Image, ImageDraw

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
OUT_BASE = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_forensics"
CAPS = {
    "cap50": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17",
    "cap51": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17",
}

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

def run_cap(cap, top_n=14, n_random=20, seed=50):
    d = CAPS[cap]
    out = os.path.join(OUT_BASE, cap)
    crops = os.path.join(out, "audit_crops"); os.makedirs(crops, exist_ok=True)
    fp = np.load(os.path.join(out, "fingerprints.npz"))
    td = np.load(os.path.join(out, "trail_detect.npz"))
    stats = json.load(open(os.path.join(out, "trail_stats.json")))
    xyz, prim_fid, n_support = fp["xyz"], fp["prim_fid"], fp["n_support"]
    camC, cam_fids = fp["camC"], fp["cam_fids"]
    cand = td["cand"]

    meta = json.load(open(f"{d}/sfm_sparse_meta.json"))
    pose_R, pose_t = {}, {}
    for p in meta["poses"]:
        if p.get("registered"):
            pose_R[p["frame_id"]] = quat_to_R(np.array(p["quat_wxyz"], float))
            pose_t[p["frame_id"]] = np.array(p["t"], float)
    # K from db camera (verified 3840x2160 == photo size)
    import sqlite3
    db = sqlite3.connect(f"file:{d}/sfm_live.db?mode=ro", uri=True)
    model, params, W, H = db.execute("SELECT model,params,width,height FROM cameras LIMIT 1").fetchone()
    db.close()
    f_, cx_, cy_ = np.frombuffer(params, dtype=np.float64)

    jpeg_of = {}
    with open(f"{d}/sfm_fed_frames.jsonl") as fh:
        for line in fh:
            j = json.loads(line)
            jpeg_of[j["frameId"]] = os.path.join(d, "photos_highres", os.path.basename(j["jpegPath"]))

    def project(fid, P):
        Xc = P @ pose_R[fid].T + pose_t[fid]
        ok = Xc[:, 2] > 1e-6
        uv = np.full((len(P), 2), np.nan)
        uv[ok, 0] = f_ * Xc[ok, 0] / Xc[ok, 2] + cx_
        uv[ok, 1] = f_ * Xc[ok, 1] / Xc[ok, 2] + cy_
        vis = ok & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
        return uv, vis

    def pick_frame(mem):
        fids = [int(prim_fid[pi]) for pi in mem if n_support[pi] > 0 and int(prim_fid[pi]) in pose_R]
        cands = [f for f, _ in Counter(fids).most_common(5)] if fids else []
        cen = xyz[mem].mean(0)
        order = np.argsort(np.linalg.norm(camC - cen, axis=1))
        cands += [int(cam_fids[i]) for i in order[:20]]
        best, best_vis = None, -1
        for fid in cands:
            if fid not in pose_R: continue
            if fid not in jpeg_of or not os.path.exists(jpeg_of[fid]): continue
            _, vis = project(fid, xyz[mem])
            if vis.sum() > best_vis:
                best, best_vis = fid, int(vis.sum())
            if best_vis == len(mem): break
        if best is None or best_vis <= 0:  # fall back: search every frame
            for fid in sorted(pose_R):
                if fid not in jpeg_of or not os.path.exists(jpeg_of[fid]): continue
                _, vis = project(fid, xyz[mem])
                if vis.sum() > best_vis:
                    best, best_vis = fid, int(vis.sum())
        return best, best_vis

    def save_crop(tag, mem):
        fid, nvis = pick_frame(mem)
        if fid is None or nvis == 0:
            return {"tag": tag, "skip": "no frame sees members"}
        uv, vis = project(fid, xyz[mem])
        img = Image.open(jpeg_of[fid]).convert("RGB")
        dr = ImageDraw.Draw(img)
        for (u, v), ok in zip(uv, vis):
            if ok:
                dr.ellipse([u-14, v-14, u+14, v+14], outline=(255, 0, 0), width=5)
        us, vs = uv[vis, 0], uv[vis, 1]
        m = 260
        x0, x1 = max(0, int(us.min()-m)), min(int(W), int(us.max()+m))
        y0, y1 = max(0, int(vs.min()-m)), min(int(H), int(vs.max()+m))
        if x1-x0 < 700: pad = (700-(x1-x0))//2; x0, x1 = max(0, x0-pad), min(int(W), x1+pad)
        if y1-y0 < 700: pad = (700-(y1-y0))//2; y0, y1 = max(0, y0-pad), min(int(H), y1+pad)
        crop = img.crop((x0, y0, x1, y1))
        if crop.width > 1400:
            crop = crop.resize((1400, int(crop.height*1400/crop.width)))
        path = os.path.join(crops, f"{tag}_fid{fid}.jpg")
        crop.save(path, quality=88)
        return {"tag": tag, "frame": fid, "jpeg": os.path.basename(jpeg_of[fid]),
                "n_member": len(mem), "n_visible": nvis, "crop": os.path.basename(path)}

    manifest = []
    for c in stats["clusters_ge3"][:top_n]:
        # recover full membership from cluster centroid via label lookup is heavy;
        # use member_idx_sample (<=20 pts, enough for a crop)
        mem = np.array(c["member_idx_sample"], int)
        manifest.append({**save_crop(f"cluster{c['rank']:02d}_n{c['n']}", mem),
                         "cluster": {k: c[k] for k in ("rank", "n", "centroid", "sig", "len_m", "elong", "axis_ray_angle_deg")}})
        print("cluster", c["rank"], "done", flush=True)
    rng = np.random.default_rng(seed)
    iso = np.flatnonzero(cand)
    pick = rng.choice(iso, size=min(n_random, len(iso)), replace=False)
    for i, pi in enumerate(pick):
        manifest.append({**save_crop(f"rand{i:02d}_pt{pi}", np.array([pi])),
                         "point": {"idx": int(pi), "xyz": [round(float(v), 3) for v in xyz[pi]]}})
    json.dump(manifest, open(os.path.join(out, "audit_manifest.json"), "w"), indent=2)
    print(f"{cap}: {len(manifest)} audit crops", flush=True)

if __name__ == "__main__":
    for cap in (sys.argv[1:] or ["cap50", "cap51"]):
        run_cap(cap)
