#!/usr/bin/env python3.11
"""
E7 step-2: INDEPENDENT true-geometry audit of the frozen-bh8 E3 knife on cap40/41.

Runs AFTER e7_birth_discipline.py and NEVER feeds back into the rule (validation,
not calibration). For each cap it samples:

  killed   : ALL / up to 24 of the E3-risk-layer kills (cull_risk_* only; the S1
             theta/reproj culls were already user-approved in E4-B and are not
             E7's subject)
  kept     : up to 24 risk-flagged points that EARNED existence
             (keep_risk_netvisible + keep_risk_multiview, stratified)
  streaks  : up to 12 S_streak members split by kept/killed (bed-edge vertical
             column minefield - sight-line strings)
  behind   : up to 12 kept S_behind points (wall ghost-layer minefield - deep
             penetration survivors)

and projects each into the best-visible real capture photo (replay refined pose,
patched K, RAW 3840x2160 pixel coords - E4 colorize-verified projection recipe),
saving an annotated crop + contact sheets for agent visual judgment.

Minefield volumetric accounting (bedroom, HANDOFF section 10.1):
  under-bed  : bed footprint = 10cm XZ cells with >=20 pts within +-5cm of the
               bed-top y (global y-hist max); under-bed volume = footprint cells,
               y in (y_floor + 0.03, y_bedtop - 0.10)  [y up is NEGATIVE-down in
               this gauge: floor y ~ -1.16 < bed top y ~ -0.56, so the band is
               (bedtop+0.10, floor-0.03) in raw y]. Reports baseline vs candidate
               counts - the CORRECT behaviour per the RS-replication doctrine is
               "no observation under the bed => leave the hole" and any real
               points there must survive.

Sampling is seeded (rng 7). Products: audit_crops/, audit sheets, e7_audit_manifest.json.
"""
import numpy as np, json, os, sys, sqlite3
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
OUT_BASE = f"{EXP}/E7_bh8_validation"
E4B = f"{EXP}/E4_cap4041_host_replay/S1_rerun"
PHOTO_DIRS = {
    "cap40": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17",
    "cap41": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17",
}
SEED = 7
N_KILLED = 24
N_KEPT = 24
N_STREAK = 12
N_BEHIND = 12

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

def run_cap(cap):
    out = os.path.join(OUT_BASE, cap)
    crops = os.path.join(out, "audit_crops"); os.makedirs(crops, exist_ok=True)
    fp = np.load(os.path.join(out, "fingerprints.npz"))
    td = np.load(os.path.join(out, "trail_detect.npz"))
    ar = np.load(os.path.join(out, "e7_arrays.npz"), allow_pickle=True)
    xyz, prim_fid, n_support = fp["xyz"], fp["prim_fid"], fp["n_support"]
    camC, cam_fids = fp["camC"], fp["cam_fids"]
    floor_h = fp["floor_h"]
    verdict = ar["verdict"]; risk = ar["risk"]; cull = ar["cull"]; net = ar["net"]
    S_streak, S_behind, S_below = td["S_streak"], td["S_behind"], td["S_below"]

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

    def save_crop(tag, mem, color=(255, 0, 0)):
        fid, nvis = pick_frame(mem)
        if fid is None or nvis == 0:
            return {"tag": tag, "skip": "no frame sees members"}
        uv, vis = project(fid, xyz[mem])
        img = Image.open(jpeg_of[fid]).convert("RGB")
        dr = ImageDraw.Draw(img)
        for (u, v), ok in zip(uv, vis):
            if ok:
                dr.ellipse([u-16, v-16, u+16, v+16], outline=color, width=6)
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
                "n_member": len(mem), "n_visible": nvis, "crop": os.path.basename(path)}

    rng = np.random.default_rng(SEED)
    manifest = {"cap": cap, "seed": SEED, "groups": {}}

    def meta_of(pi):
        return {"idx": int(pi), "xyz": [round(float(v), 3) for v in xyz[pi]],
                "verdict": str(verdict[pi]), "n_support": int(n_support[pi]),
                "net_vote": None if not np.isfinite(net[pi]) else int(net[pi]),
                "floor_h": round(float(floor_h[pi]), 3),
                "sig": "".join(c for c, m in zip("BbSo", (S_behind[pi], S_below[pi], S_streak[pi], td["S_out"][pi])) if m)}

    def sample_group(name, idx_pool, n, color):
        idx_pool = np.asarray(idx_pool)
        if len(idx_pool) == 0:
            manifest["groups"][name] = {"n_pool": 0, "items": []}
            return
        pick = idx_pool if len(idx_pool) <= n else rng.choice(idx_pool, size=n, replace=False)
        items = []
        for i, pi in enumerate(sorted(pick)):
            r = save_crop(f"{name}{i:02d}_pt{pi}", np.array([pi]), color)
            r["point"] = meta_of(pi)
            items.append(r)
        manifest["groups"][name] = {"n_pool": int(len(idx_pool)), "items": items}
        print(f"{cap} {name}: {len(items)} crops (pool {len(idx_pool)})", flush=True)

    killed_e3 = np.flatnonzero(np.char.startswith(verdict.astype(str), "cull_risk_"))
    kept_net = np.flatnonzero(verdict == "keep_risk_netvisible")
    kept_mv = np.flatnonzero(verdict == "keep_risk_multiview")
    streak_kept = np.flatnonzero(S_streak & ~cull)
    streak_killed = np.flatnonzero(S_streak & cull)
    behind_kept = np.flatnonzero(S_behind & ~cull & risk)

    sample_group("killed", killed_e3, N_KILLED, (255, 40, 40))
    sample_group("keptnet", kept_net, N_KEPT // 2, (0, 220, 0))
    sample_group("keptmv", kept_mv, N_KEPT - N_KEPT // 2, (0, 220, 0))
    sample_group("streakkept", streak_kept, N_STREAK // 2, (0, 200, 255))
    sample_group("streakkill", streak_killed, N_STREAK // 2, (255, 120, 0))
    sample_group("behindkept", behind_kept, N_BEHIND, (255, 255, 0))

    # ---- under-bed minefield volumetric accounting ----
    y = xyz[:, 1]
    lo, hi = np.percentile(y, [0.5, 99.5])
    bins = np.arange(lo, hi + 0.005, 0.005)
    hc, ed = np.histogram(y, bins=bins)
    pk = int(np.argmax(hc))
    y_bedtop = 0.5 * (ed[pk] + ed[pk+1])
    y_floor = float(-fp["plane_d"])
    slab = np.abs(y - y_bedtop) <= 0.05
    cell = 0.10
    cx = np.floor(xyz[slab, 0] / cell).astype(np.int64)
    cz = np.floor(xyz[slab, 2] / cell).astype(np.int64)
    cnt = Counter(zip(cx.tolist(), cz.tolist()))
    foot = {k for k, v in cnt.items() if v >= 20}
    pcx = np.floor(xyz[:, 0] / cell).astype(np.int64)
    pcz = np.floor(xyz[:, 2] / cell).astype(np.int64)
    in_foot = np.array([(a, b) in foot for a, b in zip(pcx.tolist(), pcz.tolist())])
    under = in_foot & (y > y_bedtop + 0.10) & (y < y_floor - 0.03)
    under_idx = np.flatnonzero(under)
    ub = {"y_bedtop": round(float(y_bedtop), 3), "y_floor": round(y_floor, 3),
          "n_footprint_cells_10cm": len(foot),
          "baseline_underbed_pts": int(under.sum()),
          "killed_underbed_pts": int((under & cull).sum()),
          "kept_underbed_pts": int((under & ~cull).sum()),
          "underbed_risk_flagged": int((under & risk).sum()),
          "doctrine": "no obs under bed => hole is correct; hallucinated points there should be caught; REAL bed-frame/under-bed floor edge points must survive"}
    manifest["underbed_minefield"] = ub
    print(f"{cap} underbed: {json.dumps(ub)}", flush=True)
    sample_group("underbedkept", np.flatnonzero(under & ~cull), 10, (255, 0, 255))
    sample_group("underbedkill", np.flatnonzero(under & cull), 6, (255, 120, 0))

    # ---- contact sheets (6 per row grid) ----
    def sheet(name, items, path):
        imgs = [Image.open(os.path.join(crops, it["crop"])) for it in items if "crop" in it]
        if not imgs: return
        tw = 420
        thumbs = []
        for im, it in zip(imgs, [it for it in items if "crop" in it]):
            t = im.resize((tw, int(im.height * tw / im.width)))
            dr = ImageDraw.Draw(t)
            p = it["point"]
            lbl = f"{it['tag']} v={p['verdict'].replace('keep_risk_','K:').replace('cull_risk_','X:')} ns={p['n_support']} net={p['net_vote']} fh={p['floor_h']}"
            dr.rectangle([0, 0, tw, 34], fill=(0, 0, 0))
            dr.text((4, 4), lbl, fill=(255, 255, 0))
            thumbs.append(t)
        cols = 4
        rows = (len(thumbs) + cols - 1) // cols
        rh = max(t.height for t in thumbs)
        sh = Image.new("RGB", (cols * tw, rows * rh), (20, 20, 20))
        for i, t in enumerate(thumbs):
            sh.paste(t, ((i % cols) * tw, (i // cols) * rh))
        sh.save(path, quality=85)
        print(f"sheet {os.path.basename(path)} ({len(thumbs)})", flush=True)

    for name, g in manifest["groups"].items():
        if g["items"]:
            sheet(name, g["items"], os.path.join(out, f"audit_sheet_{name}_{cap}.jpg"))

    json.dump(manifest, open(os.path.join(out, "e7_audit_manifest.json"), "w"), indent=2)
    print(f"{cap} audit manifest written", flush=True)

if __name__ == "__main__":
    for cap in (sys.argv[1:] or ["cap40", "cap41"]):
        run_cap(cap)
    print("E7 AUDIT CROPS DONE", flush=True)
