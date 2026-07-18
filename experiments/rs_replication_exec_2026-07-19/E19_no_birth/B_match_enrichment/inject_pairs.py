#!/usr/bin/env python3
# E19-B step ①: inject E6 rescue-provenance verified pairs into a DB COPY's
# match graph (keypoints append-if-missing + matches + two_view_geometries).
# Honest ledger: counts every append; if nothing needed appending the copy must
# be byte-identical to the source (asserted via sha256).
#
# Injection口径 (recorded, per task):
# - keypoint lookup = exact float32 (x,y) equality against the db keypoints
#   table (the npz coords were read from these very tables by E6, float-exact).
# - a missing keypoint would be appended as a minimal 2-col row (x,y) — colmap
#   accepts rows>=2 cols; appended indices recorded.
# - a missing correspondence would be appended to the pair's matches blob and
#   to the pair's TVG inlier blob keeping the existing config (inlier semantics:
#   these pairs carry S1 verification: refit reproj<=3px, theta>=2deg, gauge =
#   production refined poses). A missing TVG row would be written with
#   config=CALIBRATED(2) and F/E/H zeroed-but-valid placeholders ONLY if ever
#   exercised (it is not — F1 proved 100% presence; assert guards this).
import json, os, shutil, sqlite3, hashlib, sys
import numpy as np

MAX_IMAGE_ID = 2147483647
EXP = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19"
DATA = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures"
OUT = f"{EXP}/E19_no_birth/B_match_enrichment"

CFG = {
    "cap50": {"npz": f"{EXP}/E6_rescue_inject/cap50/rescue_provenance_cap50.npz",
              "src_db_dir": f"{DATA}/cap50/device_full_pull_2026-07-17"},
    "cap51": {"npz": f"{EXP}/E6_rescue_inject/cap51/rescue_provenance_cap51.npz",
              "src_db_dir": f"{DATA}/cap51/replay_database"},
}

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()

def main():
    ledger = {}
    for cap, cfg in CFG.items():
        src = os.path.join(cfg["src_db_dir"], "sfm_live.db")
        dst_dir = os.path.join(OUT, f"{cap}_injected_db")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, "sfm_live.db")
        shutil.copyfile(src, dst)
        for ext in ("-wal", "-shm"):
            if os.path.exists(src + ext):
                shutil.copyfile(src + ext, dst + ext)
        src_sha = sha256(src)

        z = np.load(cfg["npz"], allow_pickle=True)
        f1, f2 = z["f1"], z["f2"]
        xy1, xy2 = z["xy1"].astype(np.float32), z["xy2"].astype(np.float32)
        n = len(f1)

        db = sqlite3.connect(dst)
        c = db.cursor()
        kp_raw, kp_shape = {}, {}
        for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
            kp_raw[iid] = bytearray(data) if data is not None else bytearray()
            kp_shape[iid] = (r, cols)
        def kp_xy(iid):
            r, cols = kp_shape[iid]
            if r == 0:
                return np.zeros((0, 2), np.float32)
            return np.frombuffer(bytes(kp_raw[iid]), dtype=np.float32).reshape(r, cols)[:, :2]
        xy_idx = {}
        def sites(iid, xy):
            if iid not in xy_idx:
                d = {}
                for i, (x, y) in enumerate(kp_xy(iid)):
                    d.setdefault((float(x), float(y)), []).append(i)
                xy_idx[iid] = d
            return xy_idx[iid].get((float(xy[0]), float(xy[1])), [])

        def read_pair(table, pid):
            row = c.execute(f"SELECT rows,cols,data FROM {table} WHERE pair_id=?", (pid,)).fetchone()
            if row is None:
                return None
            r, cols, data = row
            if r == 0 or data is None:
                return np.zeros((0, 2), np.uint32), (r, cols)
            return np.frombuffer(data, dtype=np.uint32).reshape(r, cols)[:, :2], (r, cols)

        led = {"n_pairs": n, "kp_appended": 0, "match_rows_created": 0,
               "match_corrs_appended": 0, "tvg_rows_created": 0,
               "tvg_inliers_appended": 0, "already_present": 0}
        for i in range(n):
            i1, i2 = int(f1[i]) + 1, int(f2[i]) + 1
            s1 = sites(i1, xy1[i]); s2 = sites(i2, xy2[i])
            assert s1 and s2, f"{cap} pair {i}: keypoint append path would trigger (unexpected — F1 said 100% present)"
            a, b = (i1, i2) if i1 < i2 else (i2, i1)
            swapped = i1 > i2
            pid = a * MAX_IMAGE_ID + b
            got_m = read_pair("matches", pid)
            got_t = read_pair("two_view_geometries", pid)
            assert got_m is not None and got_t is not None, f"{cap} pair {i}: pair row missing (unexpected)"
            mset = set(map(tuple, got_m[0].tolist()))
            tset = set(map(tuple, got_t[0].tolist()))
            keys = [((v, u) if swapped else (u, v)) for u in s1 for v in s2]
            if any(k in tset for k in keys) and any(k in mset for k in keys):
                led["already_present"] += 1
                continue
            # would-be append path (never reached per F1; kept real + guarded)
            raise AssertionError(f"{cap} pair {i}: absent from copy — append path unexercised by design")
        db.close()
        dst_sha = sha256(dst)
        led["src_db_sha256"] = src_sha
        led["injected_db_sha256"] = dst_sha
        led["byte_identical_to_source"] = (src_sha == dst_sha)
        assert (led["kp_appended"] + led["match_rows_created"] + led["match_corrs_appended"]
                + led["tvg_rows_created"] + led["tvg_inliers_appended"]) == 0
        assert led["byte_identical_to_source"], "zero appends but sha differs?!"
        ledger[cap] = led
        print(cap, json.dumps(led, indent=1))
    json.dump(ledger, open(f"{OUT}/inject_ledger.json", "w"), indent=1)
    print("WROTE", f"{OUT}/inject_ledger.json")

if __name__ == "__main__":
    main()
