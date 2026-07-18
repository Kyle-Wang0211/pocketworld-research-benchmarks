#!/usr/bin/env python3.11
"""
E7 step-2b: crops for the bh3-vs-bh8 DIFFERENTIAL points (killed at spec-faithful
bh=3, spared at frozen bh=8; bh3_vs_bh8_diffset.json). If these are real geometry,
the new scene independently reproduces cap50's红线 (bh=3 kills true geometry) and
bh>=8 is NOT a cap50-only artifact. Agent-judged crops; no rule feedback.
"""
import numpy as np, json, os, sys, sqlite3
from collections import Counter
from PIL import Image, ImageDraw

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
OUT_BASE = f"{EXP}/E7_bh8_validation"
E4B = f"{EXP}/E4_cap4041_host_replay/S1_rerun"
PHOTO_DIRS = {
    "cap40": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17",
    "cap41": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17",
}

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

diffset = json.load(open(os.path.join(OUT_BASE, "bh3_vs_bh8_diffset.json")))
for cap in (sys.argv[1:] or ["cap40", "cap41"]):
    out = os.path.join(OUT_BASE, cap)
    crops = os.path.join(out, "audit_crops")
    fp = np.load(os.path.join(out, "fingerprints.npz"))
    xyz, prim_fid, n_support = fp["xyz"], fp["prim_fid"], fp["n_support"]
    camC, cam_fids = fp["camC"], fp["cam_fids"]
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

    items = []
    for i, (pis, info) in enumerate(sorted(diffset[cap].items(), key=lambda kv: int(kv[0]))):
        pi = int(pis)
        mem = np.array([pi])
        fids = [int(prim_fid[pi])] if int(prim_fid[pi]) in pose_R else []
        cen = xyz[pi]
        order = np.argsort(np.linalg.norm(camC - cen, axis=1))
        fids += [int(cam_fids[k]) for k in order[:25]]
        best, best_vis = None, 0
        for fid in fids:
            if fid not in pose_R or fid not in jpeg_of: continue
            _, vis = project(fid, mem.reshape(-1) if False else xyz[mem])
            if vis.sum() > best_vis: best, best_vis = fid, int(vis.sum())
            if best_vis: break
        if best is None:
            items.append({"pt": pi, "skip": "not visible"}); continue
        uv, vis = project(best, xyz[mem])
        img = Image.open(jpeg_of[best]).convert("RGB")
        dr = ImageDraw.Draw(img)
        u, v = uv[0]
        dr.ellipse([u-16, v-16, u+16, v+16], outline=(255, 160, 0), width=6)
        m = 300
        x0, x1 = max(0, int(u-m)), min(int(W), int(u+m))
        y0, y1 = max(0, int(v-m)), min(int(H), int(v+m))
        crop = img.crop((x0, y0, x1, y1))
        tag = f"bh3diff{i:02d}_pt{pi}"
        path = os.path.join(crops, f"{tag}_fid{best}.jpg")
        crop.save(path, quality=86)
        items.append({"pt": pi, "tag": tag, "crop": os.path.basename(path), "frame": best, **info})
    # sheet
    thumbs = []
    tw = 420
    for it in items:
        if "crop" not in it: continue
        t = Image.open(os.path.join(crops, it["crop"])).resize((tw, tw))
        dr = ImageDraw.Draw(t)
        dr.rectangle([0, 0, tw, 34], fill=(0, 0, 0))
        dr.text((4, 4), f"{it['tag']} hs={it['hs']} ns={it['ns']} fh={it['fh']}", fill=(255, 255, 0))
        thumbs.append(t)
    if thumbs:
        cols = 4
        rows = (len(thumbs)+cols-1)//cols
        sh = Image.new("RGB", (cols*tw, rows*tw), (20, 20, 20))
        for i, t in enumerate(thumbs):
            sh.paste(t, ((i % cols)*tw, (i//cols)*tw))
        sh.save(os.path.join(out, f"audit_sheet_bh3diff_{cap}.jpg"), quality=85)
    json.dump(items, open(os.path.join(out, "bh3diff_manifest.json"), "w"), indent=1)
    print(cap, "bh3diff crops:", len([i for i in items if "crop" in i]), flush=True)
