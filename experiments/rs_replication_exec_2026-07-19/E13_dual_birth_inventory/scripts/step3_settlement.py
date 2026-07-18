#!/usr/bin/env python3.11
"""E13 step3 — §5.1 dual-birth inventory settlement on the off baseline.

Semantics (dossier §5.1 + SYNTHESIS S1-S6 + E12 lessons, arrival order BANNED):
  * family = connected component of surviving points linked by bit-identical
    (frame, x, y) sites (step1 identity).
  * winner per family = geometric quality: median pairwise parallax angle
    (primary, 0.1 deg tie tolerance) -> track length -> mean reproj error.
    point3D id / birth order NEVER touches the ordering; full ties are left
    unsettled (kept, honest).
  * decisive loser: score = (len_L/len_W) * exclusive_obs_ratio_L <= THR.
    exclusive ratio = fraction of L's observations whose site is not occupied
    by any other surviving family member. Above THR -> ambiguous, kept.
  * loser disposal: per-observation gate to winner (same-frame dedup ->
    positive depth -> reproj <= 4px at frozen winner position -> viewing-angle
    < 60 deg); passing obs transfer, failing obs drop; loser dies.
  * frozen production poses + frozen winner positions -> zero warp by
    construction. Coverage guard: a kill that would empty a 2cm cover cell is
    atomically vetoed (E11 precedent).
  * small steps: per round settle at most 35% of decisive losers (lowest score
    first), recompute families/support, до convergence (max 8 rounds).
"""
import json
import math
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import (E13, OFF_RUN, load_plane, qvec2rot, read_cameras_bin,
                     read_images_bin_full, write_ply)

GATE_PX = 4.0
VIEW_COS = 0.5           # 60 deg
ANGLE_TIE_DEG = 0.1
STEP_FRAC = 0.35
MAX_ROUNDS = 8
COVER_SLAB = 0.03
CELL_COVER = 0.02
TRUE_LO, TRUE_HI = -0.0075, 0.0125
GHOST_LO, GHOST_HI = -0.045, -0.020


class DSU:
    def __init__(self, n):
        self.p = np.arange(n)

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def median_parallax_deg(X, cam_centers):
    if len(cam_centers) < 2:
        return 0.0
    rays = cam_centers - X
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    angs = []
    for i in range(len(rays)):
        for j in range(i + 1, len(rays)):
            c = float(np.clip(rays[i] @ rays[j], -1.0, 1.0))
            angs.append(math.degrees(math.acos(c)))
    return float(np.median(angs))


def run(cap, thr, save_artifacts):
    t0 = time.time()
    z = np.load(f"{E13}/analysis/step1_cache_{cap}.npz")
    ids, xyz, err, fh = z["ids"], z["xyz"], z["err"], z["fh"]
    obs_pt, obs_iid, obs_kp, obs_site = z["obs_pt"], z["obs_iid"], z["obs_kp"], z["obs_site"]
    npts = len(ids)
    images = read_images_bin_full(f"{OFF_RUN[cap]}/images.bin")
    cams = read_cameras_bin(f"{OFF_RUN[cap]}/cameras.bin")
    fcxcy = {}
    Rt = {}
    C = {}
    for iid, im in images.items():
        R = qvec2rot(im["qvec"] / np.linalg.norm(im["qvec"]))
        Rt[iid] = (R, im["tvec"])
        C[iid] = -R.T @ im["tvec"]
        f, cx, cy = cams[im["camera_id"]]["params"]
        fcxcy[iid] = (f, cx, cy)

    # per-point track structures (mutable: winners can grow)
    tr_iid = [[] for _ in range(npts)]
    tr_kp = [[] for _ in range(npts)]
    tr_site = [[] for _ in range(npts)]
    for o in range(len(obs_pt)):
        p = obs_pt[o]
        tr_iid[p].append(int(obs_iid[o]))
        tr_kp[p].append(int(obs_kp[o]))
        tr_site[p].append(int(obs_site[o]))

    alive = np.ones(npts, bool)

    # coverage grid guard (point-level, raw production frame)
    in_cover = np.abs(fh) <= COVER_SLAB
    cell_of = {}
    cover_cnt = defaultdict(int)
    for p in np.flatnonzero(in_cover):
        cell = (int(np.floor(xyz[p, 0] / CELL_COVER)), int(np.floor(xyz[p, 2] / CELL_COVER)))
        cell_of[p] = cell
        cover_cnt[cell] += 1

    kills = []
    vetoes = []
    rounds_log = []
    tie_unsettled_total = 0

    for rnd in range(1, MAX_ROUNDS + 1):
        # --- rebuild site occupancy over survivors
        site_occ = defaultdict(set)
        for p in np.flatnonzero(alive):
            for s in tr_site[p]:
                site_occ[s].add(p)
        # --- families
        dsu = DSU(npts)
        for s, occ in site_occ.items():
            occ = list(occ)
            for q in occ[1:]:
                dsu.union(occ[0], q)
        fams = defaultdict(list)
        for p in np.flatnonzero(alive):
            fams[dsu.find(p)].append(p)
        families = [v for v in fams.values() if len(v) >= 2]

        # --- score candidates
        cands = []
        tie_unsettled = 0
        for fam in families:
            meta = []
            for p in fam:
                cc = np.array([C[i] for i in tr_iid[p]])
                ang = median_parallax_deg(xyz[p], cc)
                meta.append((p, ang, len(tr_iid[p]), float(err[p])))
            # geometric-quality order, arrival order banned
            meta.sort(key=lambda m: (-round(m[1] / ANGLE_TIE_DEG), -m[2], m[3], -m[1]))
            top = meta[0]
            full_tie = [m for m in meta[1:]
                        if round(m[1] / ANGLE_TIE_DEG) == round(top[1] / ANGLE_TIE_DEG)
                        and m[2] == top[2] and m[3] == top[3]]
            if full_tie:
                tie_unsettled += 1
                continue  # cannot name a winner without arrival order -> keep all
            W, angW = top[0], top[1]
            for (L, angL, lenL, errL) in meta[1:]:
                support_ratio = lenL / top[2]
                others = [q for q in fam if q != L]
                excl = sum(1 for s in tr_site[L] if not any(q in site_occ[s] for q in others))
                exclusive = excl / max(len(tr_site[L]), 1)
                score = support_ratio * exclusive
                if score <= thr:
                    cands.append((score, L, W, angL, angW, support_ratio, exclusive))
        tie_unsettled_total = tie_unsettled
        if not cands:
            rounds_log.append({"round": rnd, "families": len(families), "candidates": 0, "settled": 0})
            break
        cands.sort(key=lambda c: c[0])
        batch = cands[:max(1, int(math.ceil(len(cands) * STEP_FRAC)))]

        settled = 0
        for score, L, W, angL, angW, sr, ex in batch:
            if not alive[L] or not alive[W]:
                continue
            # coverage guard (atomic veto)
            if L in cell_of and cover_cnt[cell_of[L]] == 1:
                vetoes.append({"loser": int(L), "winner": int(W), "round": rnd, "reason": "cover-cell-empty"})
                continue
            # transfer gate per observation
            W_frames = set(tr_iid[W])
            XW = xyz[W]
            dirs = np.array([C[i] for i in tr_iid[W]]) - XW
            dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
            mean_dir = dirs.mean(0)
            mean_dir /= np.linalg.norm(mean_dir)
            n_tr = n_dup = n_gate = 0
            for iid, kp, s in zip(tr_iid[L], tr_kp[L], tr_site[L]):
                if iid in W_frames:
                    n_dup += 1
                    continue
                R, t = Rt[iid]
                xc = R @ XW + t
                if xc[2] <= 0:
                    n_gate += 1
                    continue
                f, cx, cy = fcxcy[iid]
                u = f * xc[0] / xc[2] + cx
                v = f * xc[1] / xc[2] + cy
                oxy = images[iid]["xys"][kp]
                rp = math.hypot(u - oxy[0], v - oxy[1])
                if rp > GATE_PX:
                    n_gate += 1
                    continue
                nd = C[iid] - XW
                nd /= np.linalg.norm(nd)
                if nd @ mean_dir < VIEW_COS:
                    n_gate += 1
                    continue
                tr_iid[W].append(iid)
                tr_kp[W].append(kp)
                tr_site[W].append(s)
                W_frames.add(iid)
                n_tr += 1
            alive[L] = False
            if L in cell_of:
                cover_cnt[cell_of[L]] -= 1
            kills.append({
                "loser": int(L), "winner": int(W), "round": rnd,
                "score": round(score, 4), "support_ratio": round(sr, 4), "exclusive": round(ex, 4),
                "ang_L": round(angL, 3), "ang_W": round(angW, 3),
                "len_L": len(tr_kp[L]), "len_W_before": len(tr_iid[W]) - n_tr,
                "err_L": round(float(err[L]), 4), "err_W": round(float(err[W]), 4),
                "fh_L_mm": round(float(fh[L]) * 1000, 2), "fh_W_mm": round(float(fh[W]) * 1000, 2),
                "n_transfer": n_tr, "n_drop_dup": n_dup, "n_drop_gate": n_gate,
            })
            settled += 1
        rounds_log.append({"round": rnd, "families": len(families), "candidates": len(cands),
                           "settled": settled, "vetoes_so_far": len(vetoes),
                           "tie_unsettled_families": tie_unsettled})

    # --- conservation audit
    tot_obs_losers = sum(k["len_L"] for k in kills)
    tot_tr = sum(k["n_transfer"] for k in kills)
    tot_drop = sum(k["n_drop_dup"] + k["n_drop_gate"] for k in kills)
    assert tot_obs_losers == tot_tr + tot_drop, "observation conservation FAILED"
    assert int((~alive).sum()) == len(kills), "point conservation FAILED"

    # --- band decomposition of kills
    def band(v_mm):
        v = v_mm / 1000
        if TRUE_LO <= v < TRUE_HI:
            return "true_floor"
        if GHOST_LO <= v < GHOST_HI:
            return "ghost_band"
        if -0.045 <= v < -0.010:
            return "mid_fat"
        if v < -0.100:
            return "below"
        return "other"

    kb = defaultdict(int)
    cross_layer_kills = 0
    same_layer_kills = 0
    miskill_suspects = []
    for k in kills:
        kb[band(k["fh_L_mm"])] += 1
        if abs(k["fh_L_mm"] - k["fh_W_mm"]) < 15:
            same_layer_kills += 1
        else:
            cross_layer_kills += 1
        if band(k["fh_L_mm"]) == "true_floor" and abs(k["fh_W_mm"] - k["fh_L_mm"]) > 15:
            miskill_suspects.append(k)

    summary = {
        "cap": cap, "thr": thr, "rounds": rounds_log,
        "n_before": int(npts), "n_killed": len(kills), "n_after": int(alive.sum()),
        "vetoes": len(vetoes), "tie_unsettled_families_last_round": tie_unsettled_total,
        "obs_conservation": {"loser_obs": tot_obs_losers, "transferred": tot_tr,
                             "dropped_dup": sum(k["n_drop_dup"] for k in kills),
                             "dropped_gate": sum(k["n_drop_gate"] for k in kills)},
        "kills_by_band_of_loser": dict(kb),
        "same_layer_kills(|dfh|<15mm)": same_layer_kills,
        "cross_layer_kills(|dfh|>=15mm)": cross_layer_kills,
        "true_floor_miskill_suspects(loser_true&winner_far)": len(miskill_suspects),
        "wall_s": round(time.time() - t0, 1),
    }
    print(json.dumps(summary, indent=1))
    json.dump({"summary": summary, "kills": kills, "vetoes": vetoes},
              open(f"{E13}/analysis/settlement_{cap}_thr{thr}.json", "w"), indent=1)

    if save_artifacts:
        np.savez_compressed(f"{E13}/analysis/settlement_{cap}_main.npz",
                            alive=alive, kills_loser=np.array([k["loser"] for k in kills], np.int64),
                            kills_winner=np.array([k["winner"] for k in kills], np.int64))
    return summary


if __name__ == "__main__":
    all_s = {}
    for cap in ("cap51", "cap50"):
        for thr in (0.5, 0.35, 0.65):
            all_s[f"{cap}_thr{thr}"] = run(cap, thr, save_artifacts=(thr == 0.5))
    json.dump(all_s, open(f"{E13}/analysis/settlement_sensitivity.json", "w"), indent=1)
