#!/usr/bin/env python3
"""E20-C fix-A rehearsal (cap50): repay the CERTIFIED schedule's starved debt.

Debt definition (E20-B db_debt_audit semantics): temporal pairs with frame
distance 1..12 (K12 nominal live schedule) that have NO matches row in the
final device db. NOT arbitrary spatial pairs (E20-A, user-rejected) — only
pairs the pipeline itself intended to match. Count must reconcile to the
banked audit (cap50: 514).

Matching/verify/inject machinery imported verbatim from A_new_matching/s1
(colmap mutual match + production-pose Sampson<3px + >=15 inliers).
"""
import importlib.util, json, os, shutil, sqlite3, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.normpath(os.path.join(HERE, "..", "A_new_matching"))
spec = importlib.util.spec_from_file_location("s1", os.path.join(A, "s1_select_and_match.py"))
s1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s1)

CAP = "cap50"
K_WINDOW = 12
AUDIT = json.load(open(os.path.normpath(os.path.join(HERE, "..", "B_starvation_attribution", "db_debt_audit.json"))))
EXPECTED_DEBT = AUDIT[CAP]["never_matched_temporal_pairs_K12"]

cfg = s1.CFG[CAP]
meta = json.load(open(f"{cfg['meta_dir']}/sfm_sparse_meta.json"))
assert meta.get("refined") is True
poses = {}
for p in meta["poses"]:
    if p.get("registered"):
        poses[p["frame_id"]] = (s1.quat_to_R(np.array(p["quat_wxyz"])), np.array(p["t"]))

src = cfg["src_db"]
src_sha = s1.sha256(src)
db = sqlite3.connect(f"file:{src}?mode=ro&immutable=1", uri=True)
c = db.cursor()
cams = c.execute("SELECT camera_id, model, width, height, params FROM cameras").fetchall()
assert len(cams) == 1 and cams[0][1] == 0
f_, cx_, cy_ = np.frombuffer(cams[0][4], np.float64)[:3]
K = np.array([[f_, 0, cx_], [0, f_, cy_], [0, 0, 1]])
Kinv = np.linalg.inv(K)

img_ids = [r[0] for r in c.execute("SELECT image_id FROM images ORDER BY image_id")]
existing = set()
for (pid,) in c.execute("SELECT pair_id FROM matches"):
    existing.add((pid // s1.MAX_IMAGE_ID, pid % s1.MAX_IMAGE_ID))

# ---- debt selection: temporal 1..K_WINDOW, never matched (regardless of pose) ----
debt_all = []
for a in range(len(img_ids)):
    i1 = img_ids[a]
    for b in range(a + 1, min(a + K_WINDOW + 1, len(img_ids))):
        i2 = img_ids[b]
        if i2 - i1 > K_WINDOW:
            continue
        if (i1, i2) not in existing:
            debt_all.append((i1, i2))
print(f"[{CAP}] regenerated K{K_WINDOW} debt pairs: {len(debt_all)} (audit banked: {EXPECTED_DEBT})")
if len(debt_all) != EXPECTED_DEBT:
    print(f"[{CAP}] !! reconciliation mismatch — proceeding, but VERDICT must explain")

cands = []
for i1, i2 in debt_all:
    f1, f2 = i1 - 1, i2 - 1
    if f1 in poses and f2 in poses:
        cands.append((i1, i2, i2 - i1))
print(f"[{CAP}] debt pairs with registered production poses (verifiable): {len(cands)}")

kp, desc = {}, {}
for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
    kp[iid] = np.frombuffer(data, np.float32).reshape(r, cols)[:, :2].astype(np.float64)
for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM descriptors"):
    desc[iid] = np.frombuffer(data, np.uint8).reshape(r, cols).astype(np.float32)
db.close()

new_pairs, stats_rows = [], []
t_match = t_verify = 0.0
for k, (i1, i2, fd) in enumerate(cands):
    t0 = time.time()
    dot = desc[i1] @ desc[i2].T
    raw = s1.colmap_mutual_match(dot)
    del dot
    t1 = time.time(); t_match += t1 - t0
    n_inl = 0
    if len(raw) > 0:
        R1, tt1 = poses[i1 - 1]
        R2, tt2 = poses[i2 - 1]
        R = R2 @ R1.T
        t = tt2 - R @ tt1
        E = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]]) @ R
        F = Kinv.T @ E @ Kinv
        s = s1.sampson(F, kp[i1][raw[:, 0]], kp[i2][raw[:, 1]])
        inl_mask = s < s1.SAMPSON_GATE_PX
        n_inl = int(inl_mask.sum())
    else:
        F = None
    t_verify += time.time() - t1
    if n_inl >= s1.MIN_INLIERS:
        new_pairs.append((i1, i2, raw, raw[inl_mask], F))
    stats_rows.append((i1, i2, fd, len(raw), n_inl, int(n_inl >= s1.MIN_INLIERS)))
    if (k + 1) % 100 == 0 or k == len(cands) - 1:
        print(f"[{CAP}] {k+1}/{len(cands)} debt matched, accepted {len(new_pairs)}, "
              f"match {t_match:.0f}s verify {t_verify:.0f}s", flush=True)

dst_dir = os.path.join(HERE, f"{CAP}_debtfix_db")
os.makedirs(dst_dir, exist_ok=True)
dst = os.path.join(dst_dir, "sfm_live.db")
if os.path.exists(dst):
    os.remove(dst)
shutil.copyfile(src, dst)
wdb = sqlite3.connect(dst)
wdb.execute("PRAGMA journal_mode=DELETE")
wc = wdb.cursor()
n_corr = n_inl_w = 0
for i1, i2, raw, inl, F in new_pairs:
    pid = i1 * s1.MAX_IMAGE_ID + i2
    assert wc.execute("SELECT COUNT(*) FROM matches WHERE pair_id=?", (pid,)).fetchone()[0] == 0
    wc.execute("INSERT INTO matches(pair_id,rows,cols,data) VALUES(?,?,?,?)",
               (pid, len(raw), 2, sqlite3.Binary(np.ascontiguousarray(raw, "<u4").tobytes())))
    F_blob = sqlite3.Binary(np.ascontiguousarray(F.T, "<f8").tobytes())
    wc.execute("INSERT INTO two_view_geometries(pair_id,rows,cols,data,config,F,E,H,qvec,tvec) "
               "VALUES(?,?,?,?,?,?,NULL,NULL,NULL,NULL)",
               (pid, len(inl), 2, sqlite3.Binary(np.ascontiguousarray(inl, "<u4").tobytes()), 3, F_blob))
    n_corr += len(raw); n_inl_w += len(inl)
wdb.commit()
wdb.execute("PRAGMA wal_checkpoint(TRUNCATE)")
wdb.close()
for ext in ("-wal", "-shm"):
    if os.path.exists(dst + ext):
        os.remove(dst + ext)

led = {
    "debt_definition": f"temporal pairs frame-dist 1..{K_WINDOW} with no matches row (certified schedule starvation)",
    "debt_regenerated": len(debt_all), "debt_audit_banked": EXPECTED_DEBT,
    "debt_verifiable_posed": len(cands),
    "accepted": len(new_pairs),
    "acceptance_rate": round(len(new_pairs) / max(len(cands), 1), 4),
    "match_corrs_written": n_corr, "tvg_inliers_written": n_inl_w,
    "src_db_sha256": src_sha, "debtfix_db_sha256": s1.sha256(dst),
    "host_match_wall_s": round(t_match, 1), "host_verify_wall_s": round(t_verify, 1),
    "capture_idle_cost_at_16ms_per_pair_s": round(0.016 * len(cands), 1),
    "gauge": "production refined meta poses, frozen K, NO Sim3 (S1 recipe)",
}
json.dump({"_meta": {"constants": {"sampson_px": s1.SAMPSON_GATE_PX, "min_inliers": s1.MIN_INLIERS,
                                   "max_ratio": s1.MAX_RATIO, "max_distance": s1.MAX_DISTANCE}},
           CAP: led}, open(os.path.join(HERE, "debt_ledger.json"), "w"), indent=1)
np.savez_compressed(os.path.join(HERE, f"debt_pairs_{CAP}.npz"),
                    stats=np.array(stats_rows, np.float64),
                    stats_cols=np.array(["i1", "i2", "frame_dist", "n_raw_mutual", "n_inlier_3px", "accepted"]))
print(f"[{CAP}] DONE {json.dumps(led, indent=1)}")
