#!/usr/bin/env python3
"""E22-s2: append LoFTR keypoints + matches/TVG into a db copy (cap51).

New keypoints appended AFTER existing SIFT rows per image (indices continue,
existing rows untouched -> all existing matches stay valid). Descriptors table
left untouched for appended rows (triangulator never reads descriptors).
For pairs that already have matches/TVG rows: concatenate (indices unique).
Output: e22_loftr_db/sfm_live.db
"""
import json, os, shutil, sqlite3
import numpy as np

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
E22 = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E22_rebirth_prototype"
SRC = f"{ROOT}/data/pocketworld_captures/cap51/replay_database/sfm_live.db"
MAX_IMAGE_ID = 2147483647

m = np.load(f"{E22}/e22_loftr_matches.npz")
pairs = sorted({tuple(map(int, k.rsplit("_", 1)[0].split("_"))) for k in m.files})
print(f"loftr pairs to inject: {len(pairs)}")

dst_dir = f"{E22}/e22_loftr_db"
os.makedirs(dst_dir, exist_ok=True)
dst = f"{dst_dir}/sfm_live.db"
if os.path.exists(dst): os.remove(dst)
shutil.copyfile(SRC, dst)
db = sqlite3.connect(dst)
db.execute("PRAGMA journal_mode=DELETE")
c = db.cursor()

# current keypoint counts + column width
kp_meta = {iid: (r, cols) for iid, r, cols in c.execute("SELECT image_id, rows, cols FROM keypoints")}
new_kps = {}   # iid -> list of (x, y)
def kp_index(iid, xy):
    new_kps.setdefault(iid, [])
    new_kps[iid].append(xy)
    return kp_meta[iid][0] + len(new_kps[iid]) - 1

n_m = n_t = 0
for i1, i2 in pairs:
    kp1 = m[f"{i1}_{i2}_kp1"]; kp2 = m[f"{i1}_{i2}_kp2"]
    idx = np.array([[kp_index(i1, p1), kp_index(i2, p2)] for p1, p2 in zip(kp1, kp2)], np.uint32)
    pid = i1 * MAX_IMAGE_ID + i2
    row = c.execute("SELECT rows, data FROM matches WHERE pair_id=?", (pid,)).fetchone()
    if row:
        old = np.frombuffer(row[1], np.uint32).reshape(row[0], 2)
        allm = np.vstack([old, idx])
        c.execute("UPDATE matches SET rows=?, data=? WHERE pair_id=?",
                  (len(allm), sqlite3.Binary(np.ascontiguousarray(allm, "<u4").tobytes()), pid))
    else:
        c.execute("INSERT INTO matches(pair_id,rows,cols,data) VALUES(?,?,?,?)",
                  (pid, len(idx), 2, sqlite3.Binary(np.ascontiguousarray(idx, "<u4").tobytes())))
    n_m += len(idx)
    trow = c.execute("SELECT rows, data, config, F FROM two_view_geometries WHERE pair_id=?", (pid,)).fetchone()
    if trow:
        old = np.frombuffer(trow[1], np.uint32).reshape(trow[0], 2) if trow[0] else np.zeros((0, 2), np.uint32)
        allt = np.vstack([old, idx])
        c.execute("UPDATE two_view_geometries SET rows=?, data=? WHERE pair_id=?",
                  (len(allt), sqlite3.Binary(np.ascontiguousarray(allt, "<u4").tobytes()), pid))
    else:
        c.execute("INSERT INTO two_view_geometries(pair_id,rows,cols,data,config,F,E,H,qvec,tvec) "
                  "VALUES(?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                  (pid, len(idx), 2, sqlite3.Binary(np.ascontiguousarray(idx, "<u4").tobytes()), 3))
    n_t += len(idx)

# extend keypoints blobs (cols preserved; extra columns zero-padded)
for iid, kps in new_kps.items():
    r, cols = kp_meta[iid]
    blob = c.execute("SELECT data FROM keypoints WHERE image_id=?", (iid,)).fetchone()[0]
    old = np.frombuffer(blob, np.float32).reshape(r, cols)
    add = np.zeros((len(kps), cols), np.float32)
    add[:, 0] = [p[0] for p in kps]; add[:, 1] = [p[1] for p in kps]
    if cols >= 4: add[:, 2] = 1.0  # scale-ish neutral (a,b,c affine layouts: a=1)
    allk = np.vstack([old, add])
    c.execute("UPDATE keypoints SET rows=?, data=? WHERE image_id=?",
              (len(allk), sqlite3.Binary(np.ascontiguousarray(allk, "<f4").tobytes()), iid))

db.commit()
db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
db.close()
for ext in ("-wal", "-shm"):
    if os.path.exists(dst + ext): os.remove(dst + ext)
print(json.dumps({"pairs": len(pairs), "match_corrs": n_m, "tvg_inliers": n_t,
                  "images_with_new_kps": len(new_kps),
                  "new_kps_total": sum(len(v) for v in new_kps.values())}, indent=1))
