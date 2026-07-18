#!/usr/bin/env python3.11
"""
E10: SUB-FLOOR VETO PRECEDENCE FIX (F2 from E7) — ordering change only, no new rule.

E3's risk-layer earn-existence rule (frozen bh=8) evaluates:
    path 1: n_support >= 3 recovered obs            -> keep_risk_multiview
    path 2: net-visibility corridor vote            -> keep/cull
with the sub-floor standing oppose (floor_h < -0.10 => every vote opposes) living
INSIDE path 2. E7 discovered (F2) that planar-mirror virtual points can be
multi-view-consistent, so on cap40/41 a slice of sub-floor points escaped through
path 1 (cap40 18, cap41 163; audited appearance = glossy-floor reflection ghosts,
fh median ~ -0.15). cap50/51 never showed this because their sub-floor risk pool
had no >=3-obs member.

THE FIX (user-approved E3 semantics, "below the floor = constructive 100% kill,
zero loss", completed for the multi-view case):
    for a risk point that survives S1:
        if floor_h < BELOW_FLOOR:  cull_risk_belowfloor      # standing veto FIRST
        elif n_support >= 3:       keep_risk_multiview       # path 1
        else:                      net-visibility vote        # path 2
Nothing else changes. Non-risk points and non-subfloor risk points keep their
frozen E3/E7 verdicts bit-for-bit.

IMPLEMENTATION = provably-equivalent delta replay on the frozen E3/E7 arrays
(e{3,7}_arrays.npz + fingerprints floor_h), NOT a from-scratch rerun. Equivalence
argument, asserted at runtime per cap:
  (i)  under the OLD ordering, every sub-floor risk point that reached path 2 was
       already culled as cull_risk_belowfloor (below=True forces all votes to -1
       and the vote list is never empty) — asserted: no keep_risk_netvisible with
       floor_h < BELOW_FLOOR exists;
  (ii) the NEW ordering only changes the verdict of sub-floor risk points that the
       old ordering kept via path 1 (keep_risk_multiview & floor_h < BELOW_FLOOR);
  (iii) all other verdicts are order-invariant.
  Hence new_full_rerun == frozen_arrays + delta, exactly.

REGRESSION: cap50/51 replayed under the same fix must be a ZERO-change no-op
(sub-floor multi-view pool empty) — asserted, not assumed.

AUDIT HOOK: the newly-killed indices are dumped for e10_audit.py which projects
every one of them (cap40 all 18; cap41 seeded sample >=24) into real capture
photos for visual judgment. HARD GATE: one true-geometry kill (sunken floor,
step, real structure below the main floor plane) = FAIL the whole fix.

KNOWN LIMIT (disclosed, not hidden): the rule assumes NO REAL MATTER below the
main floor plane. True for single-level flat interiors (all four standard caps);
WRONG for split-level / sunken floors / staircases (would mass-kill real
geometry). This is a documented applicability boundary carried into U5
generalization blind tests as a mandatory checklist item.

Products only in E10_subfloor_precedence/. No production code touched, no
commits. python3.11, serial (E9 may be compiling C++ in parallel).
"""
import numpy as np, json, os, sys, time, hashlib

MULTIVIEW_EARN = 3      # byte-identical to E3/E7
BELOW_FLOOR = -0.10     # byte-identical to E3/E7
FLOOR_SLAB = 0.06       # S1 rulers, byte-identical
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
OUT = f"{EXP}/E10_subfloor_precedence"
E7 = f"{EXP}/E7_bh8_validation"
E3 = f"{EXP}/E3_birth_discipline"
TF = f"{EXP}/TRAILS_forensics"
E4B = f"{EXP}/E4_cap4041_host_replay/S1_rerun"

CAPS = {
    # fix-target caps (bedroom, F2 leak present)
    "cap40": {"arrays": f"{E7}/cap40/e7_arrays.npz", "fp": f"{E7}/cap40/fingerprints.npz",
              "fpinfo": f"{E7}/cap40/fingerprints_info.json",
              "ply": f"{E4B}/inputs/cap40/sfm_sparse.ply", "mode": "fix"},
    "cap41": {"arrays": f"{E7}/cap41/e7_arrays.npz", "fp": f"{E7}/cap41/fingerprints.npz",
              "fpinfo": f"{E7}/cap41/fingerprints_info.json",
              "ply": f"{E4B}/inputs/cap41/sfm_sparse.ply", "mode": "fix"},
    # regression caps (living room, pool must be empty -> zero change)
    "cap50": {"arrays": f"{E3}/cap50/e3_arrays.npz", "fp": f"{TF}/cap50/fingerprints.npz",
              "fpinfo": f"{TF}/cap50/fingerprints_info.json",
              "ply": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply",
              "e3_candidate": f"{E3}/cap50/e3_candidate_cap50.ply", "mode": "regression"},
    "cap51": {"arrays": f"{E3}/cap51/e3_arrays.npz", "fp": f"{TF}/cap51/fingerprints.npz",
              "fpinfo": f"{TF}/cap51/fingerprints_info.json",
              "ply": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17/sfm_sparse.ply",
              "e3_candidate": f"{E3}/cap51/e3_candidate_cap51.ply", "mode": "regression"},
}

def log(*a): print(*a, flush=True)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def read_ply_xyzrgb(path):
    with open(path, "rb") as f:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += f.readline()
        n = int([l for l in header.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        data = np.fromfile(f, dtype=rec, count=n)
    xyz = np.stack([data["x"], data["y"], data["z"]], axis=1).astype(np.float64)
    rgb = np.stack([data["r"], data["g"], data["b"]], axis=1)
    return xyz, rgb

def write_ply_xyzrgb(path, xyz, rgb, comment):
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

def floor_metrics(xyz, y_floor):
    y = xyz[:,1]
    slab = np.abs(y - y_floor) <= FLOOR_SLAB
    P = xyz[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update({"thickness_med_cell_p90p10_m": None, "cover_cells_2cm": 0})
        return out
    cx = np.floor(P[:,0]/CELL_THICK).astype(np.int64)
    cz = np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    key = cx * 1000003 + cz
    order = np.argsort(key)
    key_s, y_s = key[order], P[order,1]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(y_s, bounds)
    spreads = [float(np.percentile(g,90) - np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    tight = np.abs(P[:,1] - y_floor) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells) * CELL_COVER * CELL_COVER, 4)
    return out

def run_cap(cap, cfg):
    t0 = time.perf_counter()
    log(f"=== {cap} ({cfg['mode']}) ===")
    out = os.path.join(OUT, cap); os.makedirs(out, exist_ok=True)
    ar = np.load(cfg["arrays"], allow_pickle=True)
    fp = np.load(cfg["fp"])
    verdict = ar["verdict"].astype(object)
    risk, cull_old, n_support = ar["risk"], ar["cull"], ar["n_support"]
    floor_h = fp["floor_h"]
    nP = len(verdict)

    # frozen input identity: fingerprints were computed on this exact PLY
    ply_sha = sha256(cfg["ply"])
    fpi = json.load(open(cfg["fpinfo"]))
    assert fpi["inputs"]["ply_sha256"] == ply_sha, f"{cap}: PLY drifted vs frozen fingerprints"
    xyz, rgb = read_ply_xyzrgb(cfg["ply"])
    assert len(xyz) == nP == len(floor_h)
    assert np.allclose(fp["xyz"], xyz)

    s1_cull = np.char.startswith(verdict.astype(str), "cull_s1_")
    subfloor = floor_h < BELOW_FLOOR
    pool_all = risk & subfloor                       # every sub-floor risk point
    pool_alive = risk & ~s1_cull & subfloor          # ...that reached the risk layer

    # ---- equivalence assertions (see docstring) ----
    # (i) old ordering already culled every sub-floor point that took path 2
    assert int(((verdict == "keep_risk_netvisible") & subfloor).sum()) == 0, \
        f"{cap}: sub-floor netvisible keeper exists - delta replay would be unsound"
    # sanity: every sub-floor risk-layer survivor is exactly a path-1 keeper
    mv_leak = (verdict == "keep_risk_multiview") & subfloor
    survivors_sub = pool_alive & ~cull_old
    assert np.array_equal(np.flatnonzero(mv_leak), np.flatnonzero(survivors_sub)), \
        f"{cap}: sub-floor survivors are not exactly the path-1 keepers"
    # path-1 keepers really have >=3 recovered obs
    if mv_leak.any():
        assert int(n_support[mv_leak].min()) >= MULTIVIEW_EARN

    # ---- the fix: standing veto outranks path 1 ----
    new_verdict = verdict.copy()
    new_verdict[mv_leak] = "cull_risk_belowfloor"     # same label as path-2 kills; delta kept separately
    cull_new = np.char.startswith(new_verdict.astype(str), "cull_")
    delta = cull_new & ~cull_old
    assert np.array_equal(np.flatnonzero(delta), np.flatnonzero(mv_leak))
    n_delta = int(delta.sum())
    log(f"{cap}: points={nP} subfloor_risk_pool(all/alive)={int(pool_all.sum())}/{int(pool_alive.sum())} "
        f"path1_leak_killed={n_delta}")

    if cfg["mode"] == "regression":
        # HARD assertion: fix is a no-op on the calibration scenes
        assert n_delta == 0, f"{cap}: regression FAIL - fix changed the calibration scene"
        e3_sha = sha256(cfg["e3_candidate"])
        stats = {
            "cap": cap, "mode": "regression",
            "inputs": {"arrays": cfg["arrays"], "fingerprints": cfg["fp"],
                       "baseline_ply": cfg["ply"], "baseline_ply_sha256": ply_sha},
            "subfloor_risk_pool_all": int(pool_all.sum()),
            "subfloor_risk_pool_alive": int(pool_alive.sum()),
            "subfloor_already_culled_path2": int((verdict == "cull_risk_belowfloor").sum()),
            "path1_multiview_subfloor_leak": 0,
            "delta_kills": 0,
            "candidate": "UNCHANGED == E3 candidate (asserted zero-delta; no duplicate PLY written)",
            "e3_candidate_path": cfg["e3_candidate"],
            "e3_candidate_sha256": e3_sha,
            "verdict": "PASS (zero change, pool empty as predicted)",
            "wall_s": round(time.perf_counter()-t0, 2),
        }
        json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=2)
        return stats

    # ---- fix caps: products ----
    keep = ~cull_new
    cand, cand_rgb = xyz[keep], rgb[keep]
    p_cand = os.path.join(out, f"e10_candidate_{cap}.ply")
    write_ply_xyzrgb(p_cand, cand, cand_rgb,
        f"E10 candidate {cap}: E7 frozen bh=8 rule with sub-floor standing veto ORDERED BEFORE "
        f"path-1 multiview earn (F2 fix, user-approved E3 sub-floor semantics); production gauge, no Sim3")
    dif_rgb = np.zeros((nP,3), np.uint8); dif_rgb[:] = (120,120,120)
    dif_rgb[risk & keep] = (0,220,0)
    dif_rgb[cull_old] = (255,40,40)
    dif_rgb[delta] = (255,220,0)                       # E10's newly killed, visually distinct
    p_diff = os.path.join(out, f"diff_{cap}.ply")
    write_ply_xyzrgb(p_diff, xyz, dif_rgb,
        f"E10 diff {cap}: yellow=NEW sub-floor precedence kills ({n_delta}), red=prior E3/E7+S1 kills, "
        f"green=risk point that earned existence, gray=non-risk kept")

    # ---- four rulers; reference = E7 candidate (the fix's own baseline) ----
    y_floor = float(-fp["plane_d"])
    e7_keep = ~cull_old
    fl_e7 = floor_metrics(xyz[e7_keep], y_floor)
    fl_new = floor_metrics(cand, y_floor)
    fl_base = floor_metrics(xyz, y_floor)
    # the fix may only touch the sub-floor pool: assert floor-slab rulers untouched
    # (fh < -0.10 is strictly below the ±0.06 slab, so slab membership cannot change)
    if n_delta:
        assert float(np.abs(xyz[delta][:,1] - y_floor).min()) >= FLOOR_SLAB, \
            "a delta kill sits inside the floor slab - sub-floor gate/ruler geometry inconsistent"
    assert fl_e7["cover_cells_2cm"] == fl_new["cover_cells_2cm"], "fix leaked into coverage ruler"
    assert fl_e7["n_floor_slab"] == fl_new["n_floor_slab"], "fix leaked into floor slab"
    cover_loss_vs_e7 = 100.0*(fl_e7["cover_cells_2cm"]-fl_new["cover_cells_2cm"])/max(fl_e7["cover_cells_2cm"],1)
    rulers = {
        "ruler_1_points": {"e7_candidate": int(e7_keep.sum()), "e10_candidate": int(len(cand)),
                           "delta": -n_delta,
                           "delta_pct_vs_e7": round(-100.0*n_delta/int(e7_keep.sum()), 3),
                           "raw_baseline": nP},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "raw_baseline": fl_base,
                                    "e7_candidate": fl_e7, "e10_candidate": fl_new,
                                    "identical_required": True},
        "ruler_3_coverage": {"e7_cells_2cm": fl_e7["cover_cells_2cm"],
                             "e10_cells_2cm": fl_new["cover_cells_2cm"],
                             "loss_pct_vs_e7": round(cover_loss_vs_e7,3),
                             "gate": "must be exactly 0 (sub-floor pool is >=10cm below the ±6cm slab)"},
        "ruler_4_wallclock_host_proxy_s": round(time.perf_counter()-t0, 2),
    }

    kill_meta = [{"idx": int(pi), "xyz": [round(float(v),3) for v in xyz[pi]],
                  "floor_h": round(float(floor_h[pi]),3), "n_support": int(n_support[pi])}
                 for pi in np.flatnonzero(delta)]
    stats = {
        "cap": cap, "mode": "fix",
        "experiment": "E10 sub-floor veto precedence over path-1 (F2 fix); ordering change only",
        "inputs": {"arrays": cfg["arrays"], "fingerprints": cfg["fp"],
                   "baseline_ply": cfg["ply"], "baseline_ply_sha256": ply_sha},
        "equivalence_proof": {
            "no_subfloor_netvisible_keeper": True,
            "subfloor_survivors_equal_path1_keepers": True,
            "hence": "delta replay == full rerun with reordered rule, bit-exact",
        },
        "subfloor_risk_pool_all": int(pool_all.sum()),
        "subfloor_risk_pool_alive": int(pool_alive.sum()),
        "previously_killed_path2": int((verdict == "cull_risk_belowfloor").sum()),
        "new_kills_path1_leak": n_delta,
        "new_kills_floor_h_median": round(float(np.median(floor_h[delta])),3) if n_delta else None,
        "new_kills_n_support_median": float(np.median(n_support[delta])) if n_delta else None,
        "verdict_counts_new": {v: int((new_verdict==v).sum()) for v in sorted(set(new_verdict.tolist()))},
        "four_rulers": rulers,
        "new_kill_points": kill_meta,
        "outputs_sha256": {os.path.basename(p): sha256(p) for p in [p_cand, p_diff]},
        "honesty": [
            "delta replay on frozen E7 arrays, equivalence asserted (see docstring) - not a from-scratch rerun",
            "same label cull_risk_belowfloor reused; the E10 delta set is preserved in e10_arrays.npz + diff yellow",
            "APPLICABILITY BOUNDARY: assumes no real matter below the main floor plane; single-level scenes only; split-level/sunken floors would be mass-killed - mandatory U5 blind-test checklist item",
            "audit gate pending e10_audit.py: ONE true-geometry kill among the delta = FAIL",
        ],
    }
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=2)
    np.savez_compressed(os.path.join(out, "e10_arrays.npz"),
                        verdict=new_verdict.astype(str), cull=cull_new, delta=delta,
                        risk=risk, n_support=n_support)
    return stats

if __name__ == "__main__":
    caps = sys.argv[1:] or ["cap40", "cap41", "cap50", "cap51"]
    allstats = {}
    ap = os.path.join(OUT, "stats_all.json")
    if os.path.exists(ap):
        allstats = json.load(open(ap))
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
    json.dump(allstats, open(ap, "w"), indent=2)
    log("E10 DONE")
