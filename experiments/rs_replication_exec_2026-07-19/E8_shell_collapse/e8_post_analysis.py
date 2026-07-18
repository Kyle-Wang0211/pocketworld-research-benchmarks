#!/usr/bin/env python3.11
"""E8 post-hoc accounting (reads E8 outputs only, writes analysis_<cap>.json):
1. thickness composition audit: per 5cm floor cell spread before/after; cells with no
   membership change must be bit-identical (proves any med shift is composition).
2. merged-group composition: stock-only / mixed / injected-only.
3. shell fate: for double-floor-band members that merged, where did the consensus land
   (out of band above / still in band / below band)?
"""
import numpy as np, json, sys
from collections import defaultdict

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
E8 = f"{EXP}/E8_shell_collapse"
FLOOR_SLAB, CELL_THICK, DBL_BAND = 0.06, 0.05, (-0.06, -0.015)

def read_ply(path):
    with open(path, "rb") as f:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += f.readline()
        n = int([l for l in header.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        data = np.fromfile(f, dtype=rec, count=n)
    return np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)

def cell_spreads(P, y_floor):
    m = np.abs(P[:,1]-y_floor) <= FLOOR_SLAB
    Q = P[m]
    cells = defaultdict(list)
    for x, y, z in Q:
        cells[(int(np.floor(x/CELL_THICK)), int(np.floor(z/CELL_THICK)))].append(y)
    return {k: (float(np.percentile(v,90)-np.percentile(v,10)), len(v)) for k, v in cells.items() if len(v) >= 8}

for cap in (sys.argv[1:] or ["cap50","cap51"]):
    s = json.load(open(f"{E8}/{cap}/stats.json"))
    y_floor = s["ruler_2_floor_thickness"]["y_floor"]
    z = np.load(f"{E8}/{cap}/collapse_provenance_{cap}.npz")
    rep_of, group_of, untouched = z["rep_of"], z["group_of"], z["untouched"]
    cons_pos, is_inj, n_obs = z["cons_pos"], z["is_inj"], z["n_obs"]
    # reconstruct BEFORE pts: v1.1 = e6 v1_1 ply (float32 ok for this audit)
    before = read_ply(f"{EXP}/E6_rescue_inject/{cap}/v1_1_candidate_{cap}.ply")
    after = read_ply(f"{E8}/{cap}/e8_candidate_{cap}.ply")
    nV = len(before)
    members = ~untouched
    # 1) thickness composition audit
    cb = cell_spreads(before, y_floor); ca = cell_spreads(after, y_floor)
    common = set(cb) & set(ca)
    # cells with unchanged membership: no member removed in cell and no consensus added in cell
    mem_cells = set()
    for p in before[members]:
        if abs(p[1]-y_floor) <= FLOOR_SLAB:
            mem_cells.add((int(np.floor(p[0]/CELL_THICK)), int(np.floor(p[2]/CELL_THICK))))
    for p in cons_pos:
        if abs(p[1]-y_floor) <= FLOOR_SLAB:
            mem_cells.add((int(np.floor(p[0]/CELL_THICK)), int(np.floor(p[2]/CELL_THICK))))
    unchanged = [k for k in common if k not in mem_cells]
    ident = sum(1 for k in unchanged if abs(cb[k][0]-ca[k][0]) < 1e-12)
    touched = [k for k in common if k in mem_cells]
    d_touched = [ca[k][0]-cb[k][0] for k in touched]
    # 2) group composition
    ngroups = int(group_of.max())+1 if (group_of >= 0).any() else 0
    comp = {"stock_only":0, "mixed":0, "injected_only":0}
    for g in range(ngroups):
        mem = np.flatnonzero(group_of == g)
        ninj = int(is_inj[mem].sum())
        comp["injected_only" if ninj==len(mem) else "stock_only" if ninj==0 else "mixed"] += 1
    # 3) shell fate — need fh; recompute from plane in TRAILS fingerprints
    fpz = np.load(f"{EXP}/TRAILS_forensics/{cap}/fingerprints.npz")
    pn, pd = fpz["plane_n"].astype(float), float(fpz["plane_d"])
    fh_before = before @ pn + pd            # float32-cast positions; band counts approx equal stats
    fh_cons = cons_pos @ pn + pd
    in_band = (fh_before >= DBL_BAND[0]) & (fh_before < DBL_BAND[1])
    band_groups = np.unique(group_of[in_band & members])
    fate = {"consensus_above_band":0, "consensus_in_band":0, "consensus_below_band":0}
    for g in band_groups:
        if g < 0: continue
        f = fh_cons[g]
        fate["consensus_above_band" if f >= DBL_BAND[1] else
             "consensus_in_band" if f >= DBL_BAND[0] else "consensus_below_band"] += 1
    out = {
        "thickness_composition_audit": {
            "n_measured_cells_common": len(common),
            "n_cells_membership_unchanged": len(unchanged),
            "n_unchanged_bitidentical_spread": ident,
            "n_cells_touched_by_merge": len(touched),
            "touched_spread_delta_m": {"med": float(np.median(d_touched)) if d_touched else None,
                                        "p10": float(np.percentile(d_touched,10)) if d_touched else None,
                                        "p90": float(np.percentile(d_touched,90)) if d_touched else None,
                                        "n_thinner": int(sum(1 for d in d_touched if d < -1e-12)),
                                        "n_thicker": int(sum(1 for d in d_touched if d > 1e-12))},
            "verdict": "med shift is composition-only iff all membership-unchanged cells are bit-identical",
        },
        "group_composition": comp,
        "band_member_group_fate": fate | {"n_groups_containing_band_members": int(len(band_groups[band_groups>=0]))},
    }
    json.dump(out, open(f"{E8}/{cap}/analysis_{cap}.json", "w"), indent=2)
    print(cap, json.dumps(out, indent=1))
