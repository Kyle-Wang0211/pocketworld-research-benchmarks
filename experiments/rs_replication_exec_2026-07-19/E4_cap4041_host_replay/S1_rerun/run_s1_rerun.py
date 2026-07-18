#!/usr/bin/env python3.11
"""E4-B: S1 unified 2-view lifecycle rerun on cap40/cap41 using the E4 HOST-REPLAY
self-consistent baseline triple (replay poses + replay finalize cloud + device db).

Why: device-delivered meta/PLY for cap40/41 are geometrically inconsistent with the
pulled db (Sampson ~15px; device finalize took the full-resolve path, gauge blown,
bbox >100m). E4-A rebuilt a self-consistent host-replay baseline (Sampson ~1px, PASS).
This script re-runs the UNTOUCHED S1 rule (build_candidate.py, imported, zero edits)
against that baseline.

Baseline triple construction per cap (written to inputs/<cap>/):
  - sfm_sparse.ply   = replay points3D.bin xyz (order == replay_finalize.ply, verified
                       max diff 2.4e-7) + HOST COLORIZE: production recipe (track obs,
                       full-res bilinear, mean over obs, round) sampled from pulled
                       photos_highres in RAW pixel coords (no EXIF rotation --
                       adjudicated on cap51_control vs device-colorized PLY:
                       raw median |dRGB| ~ 8 vs rotated ~ 55).
  - sfm_sparse_meta.json = replay images.bin poses (refined=true; frame_id = iid-1).
  - sfm_live.db      = COPY of pulled device db (+wal/shm), wal-checkpointed, with
                       cameras.params PATCHED to the replay-refined K (replay refined
                       focal: cap40 2412.83 vs db 2565.38; cap41 2362.33 vs 2566.40).
                       Source dbs untouched (md5 re-checked after run).

Honest deltas vs cap50/51 S1 runs (device baseline): baseline is host-replay, NOT the
device delivery; colors are host colorize, NOT device colorize; cap40 obs falling only
in the 3 missing JPEGs keep rgb=0 and are counted.

Writes ONLY into E4_cap4041_host_replay/S1_rerun/. python3.11.
"""
import sys, os, json, shutil, sqlite3, hashlib, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
E4 = os.path.dirname(HERE)
EXEC = os.path.dirname(E4)
ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
S1 = f"{EXEC}/S1_twoview_lifecycle"
sys.path.insert(0, S1)
sys.path.insert(0, E4)
import build_candidate as bc      # frozen S1 rule -- imported, never edited
import validate_replay as vr      # frozen bin readers
import render_views as rv         # frozen render recipe

CAPS = {
    "cap40": {
        "pull": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17",
        "runs": f"{E4}/runs/cap40",
    },
    "cap41": {
        "pull": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17",
        "runs": f"{E4}/runs/cap41",
    },
}

def log(*a): print(*a, flush=True)

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def bilinear(arr, x, y):
    H, W, _ = arr.shape
    x = np.clip(x, 0, W - 1.001); y = np.clip(y, 0, H - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = x - x0; fy = y - y0
    return (arr[y0, x0]   * ((1 - fx) * (1 - fy))[:, None]
          + arr[y0, x0+1] * (fx * (1 - fy))[:, None]
          + arr[y0+1, x0] * ((1 - fx) * fy)[:, None]
          + arr[y0+1, x0+1] * (fx * fy)[:, None])

def colorize(pts, imgs, pull):
    """Production-recipe host colorize: track obs, full-res bilinear on RAW jpeg
    pixel coords (no EXIF rotation), mean over obs, round. Returns rgb + report."""
    fed = {}
    for line in open(f"{pull}/sfm_fed_frames.jsonl"):
        j = json.loads(line); fed[j["frameId"]] = os.path.basename(j["jpegPath"])
    nP = len(pts)
    obs_by_img = {}
    for pi, (pid, xyz, rgb, err, track) in enumerate(pts):
        for iid, p2d in track:
            obs_by_img.setdefault(int(iid), []).append((pi, int(p2d)))
    sums = np.zeros((nP, 3)); cnt = np.zeros(nP)
    missing_jpegs = []
    for iid in sorted(obs_by_img):
        fid = iid - 1
        fn = fed.get(fid)
        p = f"{pull}/photos_highres/{fn}" if fn else None
        if p is None or not os.path.exists(p):
            missing_jpegs.append((fid, fn)); continue
        arr = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
        lst = obs_by_img[iid]
        pis = np.array([a for a, _ in lst]); p2ds = np.array([b for _, b in lst])
        xys = imgs[iid]["xys"]
        c = bilinear(arr, xys["x"][p2ds], xys["y"][p2ds])
        np.add.at(sums, pis, c); np.add.at(cnt, pis, 1)
    rgb = np.zeros((nP, 3), np.uint8)
    ok = cnt > 0
    rgb[ok] = np.clip(np.rint(sums[ok] / cnt[ok, None]), 0, 255).astype(np.uint8)
    rep = {"n_points": nP, "n_colorized": int(ok.sum()),
           "n_black_no_obs_jpeg": int((~ok).sum()),
           "missing_or_unfed_frames": missing_jpegs,
           "recipe": "track obs + full-res bilinear + mean + round; RAW pixel coords (no EXIF rotation; adjudicated on cap51_control: raw median|dRGB|~8 vs rotated ~55)"}
    return rgb, rep

def prepare_inputs(cap, cfg):
    ind = os.path.join(HERE, "inputs", cap)
    os.makedirs(ind, exist_ok=True)
    pull, runs = cfg["pull"], cfg["runs"]

    src_db = f"{pull}/sfm_live.db"
    src_md5 = md5(src_db)

    # 1. replay model
    pts = vr.read_points3d_bin(f"{runs}/points3D.bin")
    imgs = vr.read_images_bin(f"{runs}/images.bin")
    cams = vr.read_cameras_bin(f"{runs}/cameras.bin")
    assert len(cams) == 1
    kparams = list(cams.values())[0]["params"]
    assert list(cams.values())[0]["model"] == 0 and len(kparams) == 3

    # 2. baseline PLY = replay cloud + host colorize
    t0 = time.perf_counter()
    xyz = np.array([p[1] for p in pts])
    rgb, crep = colorize(pts, imgs, pull)
    bc.write_ply_xyzrgb(os.path.join(ind, "sfm_sparse.ply"), xyz, rgb,
        f"E4-B host-replay baseline {cap}: replay points3D.bin + host colorize (production recipe, raw coords)")
    log(f"{cap} colorize: {crep['n_colorized']}/{crep['n_points']} colorized, "
        f"{crep['n_black_no_obs_jpeg']} black, wall={time.perf_counter()-t0:.1f}s")

    # 3. meta = replay poses (frame_id = iid-1 via image name, same as validate_replay)
    poses = []
    for iid, im in sorted(imgs.items()):
        fid = int(im["name"].split("_")[1].split(".")[0])
        assert fid == iid - 1, (iid, im["name"])
        poses.append({"frame_id": fid, "registered": True,
                      "quat_wxyz": list(im["q"]), "t": list(im["t"])})
    meta = {"refined": True,
            "source": "E4 host replay images.bin (sfm_replay_bench_exe sha 7648090b..., production env face)",
            "note": "synthesized for S1 rerun; NOT the device-delivered meta (which failed self-consistency, Sampson ~15px)",
            "n_registered": len(poses), "poses": poses}
    json.dump(meta, open(os.path.join(ind, "sfm_sparse_meta.json"), "w"))

    # 4. db copy with replay-refined K patched in
    dst_db = os.path.join(ind, "sfm_live.db")
    shutil.copy(src_db, dst_db)
    for ext in ("-wal", "-shm"):
        if os.path.exists(src_db + ext):
            shutil.copy(src_db + ext, dst_db + ext)
    con = sqlite3.connect(dst_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    old = np.frombuffer(con.execute("SELECT params FROM cameras").fetchone()[0], dtype=np.float64)
    con.execute("UPDATE cameras SET params=?", (np.asarray(kparams, dtype=np.float64).tobytes(),))
    con.commit(); con.close()
    for ext in ("-wal", "-shm"):
        if os.path.exists(dst_db + ext): os.remove(dst_db + ext)
    log(f"{cap} K patch: db {list(old)} -> replay {list(kparams)}")

    prep = {"source_db": src_db, "source_db_md5_before": src_md5,
            "replay_K_patched": list(map(float, kparams)), "device_db_K": list(map(float, old)),
            "n_replay_points": len(pts), "n_registered_poses": len(poses),
            "colorize": crep}
    json.dump(prep, open(os.path.join(ind, "prepare_report.json"), "w"), indent=2, default=str)
    return src_db, src_md5

if __name__ == "__main__":
    caps = sys.argv[1:] or ["cap40", "cap41"]
    # S1 rule outputs land in S1_rerun/<cap>
    bc.OUT_BASE = HERE
    rv.BASE = HERE
    src_checks = {}
    for cap in caps:
        src_checks[cap] = prepare_inputs(cap, CAPS[cap])
        bc.CAPS[cap] = {"dir": os.path.join(HERE, "inputs", cap), "chair_roi": None}
    allstats = {}
    for cap in caps:
        allstats[cap] = bc.run_cap(cap, bc.CAPS[cap])
        rv.render_cap(cap)
    # source-db immutability re-check
    for cap, (src_db, before) in src_checks.items():
        after = md5(src_db)
        allstats[cap]["source_db_md5_unchanged"] = (before == after)
        log(f"{cap} source db md5 unchanged: {before == after}")
    json.dump(allstats, open(os.path.join(HERE, "stats_all_rerun.json"), "w"), indent=2)
    log("ALL DONE")
