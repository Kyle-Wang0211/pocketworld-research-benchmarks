#!/usr/bin/env python3.11
"""
E10 audit: project EVERY newly-killed point (cap40: all 18) and a seeded sample
(cap41: 24 of 163) into the best-visible real capture photo for visual judgment.

HARD GATE (fail-honest): every crop must show a glossy-floor / reflective-surface
mirror ghost. ONE true-geometry kill (sunken floor, step, real structure below
the main floor plane) = the whole E10 fix FAILS and is reported as such.

Projection recipe = E7 audit verbatim (replay refined pose, patched K, RAW
3840x2160 pixel coords, E4 colorize-verified). Seed = 7 (same as E7).
Extra context per crop: the point is drawn in RED; its fh (m below floor plane)
and n_support are stamped on the contact sheet.
"""
import numpy as np, json, os, sys, sqlite3
from collections import Counter
from PIL import Image, ImageDraw

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
OUT = f"{EXP}/E10_subfloor_precedence"
E7 = f"{EXP}/E7_bh8_validation"
E4B = f"{EXP}/E4_cap4041_host_replay/S1_rerun"
PHOTO_DIRS = {
    "cap40": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17",
    "cap41": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17",
}
SEED = 7
N_SAMPLE = {"cap40": None, "cap41": 24}   # None = audit every delta kill

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

def run_cap(cap):
    out = os.path.join(OUT, cap)
    crops = os.path.join(out, "audit_crops"); os.makedirs(crops, exist_ok=True)
    fp = np.load(f"{E7}/{cap}/fingerprints.npz")
    e10 = np.load(os.path.join(out, "e10_arrays.npz"), allow_pickle=True)
    xyz, prim_fid, n_support = fp["xyz"], fp["prim_fid"], fp["n_support"]
    camC, cam_fids, floor_h = fp["camC"], fp["cam_fids"], fp["floor_h"]
    delta = e10["delta"]

    inp = f"{E4B}/inputs/{cap}"
    meta = json.load(open(f"{inp}/sfm_sparse_meta.json"))
    pose_R, pose_t = {}, {}
    for p in meta["poses"]:
        if p.get("registered"):
            pose_R[p["frame_id"]] = quat_to_R(np.array(p["quat_wxyz"], float))
            pose_t[p["frame_id"]] = np.array(p["t"], float)
    db = sqlite3.connect(f"file:{inp}/sfm_live.db?mode=ro", uri=True)
    model, params, W, H = db.execute("SELECT model,params,width,height FROM cameras LIMIT 1").fetchone()
    db.close()
    f_, cx_, cy_ = np.frombuffer(params, dtype=np.float64)

    pd = PHOTO_DIRS[cap]
    jpeg_of = {}
    with open(f"{pd}/sfm_fed_frames.jsonl") as fh:
        for line in fh:
            j = json.loads(line)
            p = os.path.join(pd, "photos_highres", os.path.basename(j["jpegPath"]))
            if os.path.exists(p): jpeg_of[j["frameId"]] = p

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
        cands += [int(cam_fids[i]) for i in order[:25]]
        best, best_vis = None, -1
        for fid in cands:
            if fid not in pose_R or fid not in jpeg_of: continue
            _, vis = project(fid, xyz[mem])
            if vis.sum() > best_vis:
                best, best_vis = fid, int(vis.sum())
            if best_vis == len(mem): break
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
                dr.ellipse([u-16, v-16, u+16, v+16], outline=(255, 0, 0), width=6)
        us, vs = uv[vis, 0], uv[vis, 1]
        m = 280
        x0, x1 = max(0, int(us.min()-m)), min(int(W), int(us.max()+m))
        y0, y1 = max(0, int(vs.min()-m)), min(int(H), int(vs.max()+m))
        if x1-x0 < 760: pad = (760-(x1-x0))//2; x0, x1 = max(0, x0-pad), min(int(W), x1+pad)
        if y1-y0 < 760: pad = (760-(y1-y0))//2; y0, y1 = max(0, y0-pad), min(int(H), y1+pad)
        crop = img.crop((x0, y0, x1, y1))
        if crop.width > 1200:
            crop = crop.resize((1200, int(crop.height*1200/crop.width)))
        path = os.path.join(crops, f"{tag}_fid{fid}.jpg")
        crop.save(path, quality=86)
        return {"tag": tag, "frame": fid, "jpeg": os.path.basename(jpeg_of[fid]),
                "n_visible": nvis, "crop": os.path.basename(path)}

    rng = np.random.default_rng(SEED)
    pool = np.flatnonzero(delta)
    n = N_SAMPLE[cap]
    pick = pool if (n is None or len(pool) <= n) else np.sort(rng.choice(pool, size=n, replace=False))
    manifest = {"cap": cap, "seed": SEED, "delta_pool": int(len(pool)),
                "audited": int(len(pick)), "items": []}
    for i, pi in enumerate(pick):
        r = save_crop(f"e10kill{i:02d}_pt{pi}", np.array([pi]))
        r["point"] = {"idx": int(pi), "xyz": [round(float(v), 3) for v in xyz[pi]],
                      "floor_h": round(float(floor_h[pi]), 3), "n_support": int(n_support[pi])}
        manifest["items"].append(r)
    print(f"{cap}: {len(pick)} crops of {len(pool)} delta kills", flush=True)

    # contact sheet
    items = [it for it in manifest["items"] if "crop" in it]
    imgs = [Image.open(os.path.join(crops, it["crop"])) for it in items]
    tw = 420
    thumbs = []
    for im, it in zip(imgs, items):
        t = im.resize((tw, int(im.height * tw / im.width)))
        dr = ImageDraw.Draw(t)
        p = it["point"]
        dr.rectangle([0, 0, tw, 34], fill=(0, 0, 0))
        dr.text((4, 4), f"{it['tag']} fh={p['floor_h']} ns={p['n_support']}", fill=(255, 255, 0))
        thumbs.append(t)
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    rh = max(t.height for t in thumbs)
    sh = Image.new("RGB", (cols * tw, rows * rh), (20, 20, 20))
    for i, t in enumerate(thumbs):
        sh.paste(t, ((i % cols) * tw, (i // cols) * rh))
    sheet_path = os.path.join(out, f"audit_sheet_e10kills_{cap}.jpg")
    sh.save(sheet_path, quality=85)
    json.dump(manifest, open(os.path.join(out, "e10_audit_manifest.json"), "w"), indent=2)
    print(f"{cap}: sheet + manifest written", flush=True)

if __name__ == "__main__":
    for cap in (sys.argv[1:] or ["cap40", "cap41"]):
        run_cap(cap)
    print("E10 AUDIT CROPS DONE", flush=True)
