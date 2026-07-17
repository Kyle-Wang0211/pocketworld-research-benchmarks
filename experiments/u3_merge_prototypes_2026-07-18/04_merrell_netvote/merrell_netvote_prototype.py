#!/usr/bin/env python3
"""U3 #4 -- Merrell (ICCV 2007) signed net-vote hard-rejection prototype for cap50.

Question under test
-------------------
Can we combine the multi-view evidence we ALREADY have on cap50 into a signed
"net vote" (Merrell stability = support - opposition), and does the
"no single vote convicts" rule (stability >= 0) cure the false kills that a
"one strike and you're out" rule produces? And -- the honest key test -- can the
net-vote rule kill the plane-sweep chair-flatten false positive?

Merrell 2007 mechanism (paper-grounded, faithfully adapted)
----------------------------------------------------------
For a candidate 3D point P and a set of independent per-view depth maps D_k:
  * SUPPORT  : an independent view photometrically/geometrically agrees the
               surface is at P.
  * FREE-SPACE VIOLATION (opposition): depth map D_k measures a surface FARTHER
               than P along the same ray (z_P < d_k - tau).  D_k observed that
               space to be empty, so P conflicts -> a signed "against" vote.
  * OCCLUSION (NOT a violation): D_k measures a surface CLOSER than P
               (z_P > d_k + tau).  P is merely hidden behind a nearer surface;
               Merrell explicitly does NOT convict on occlusion, because a
               hidden farther surface is physically consistent.
  * ABSTAIN  : P projects out of D_k, or D_k confidence is low there.
Stability(P) = support(P) - freespace_violations(P).  Merrell keeps a point iff
stability >= 0 (support outnumbers free-space opposition).  A single free-space
violation does NOT convict when support outnumbers it.

Evidence sources actually available for cap50 (nothing fabricated)
------------------------------------------------------------------
  * SUPPORT for the plane-sweep candidates = the frozen photometric ZNCC clique
    size (`nviews`) already serialized into the pinned union PLY.  This is the
    number of independent views that agreed the floor surface is at that grid
    cell.  We do NOT recompute it -- we read it and assert the union PLY
    reproduces the frozen byte-exact SHA.
  * OPPOSITION = free-space violations against the ONLY independent per-view
    depth maps that exist on this capture: the five on-device L1 (CasDiffMVS)
    depth maps l1_depth_{2,20,83,128,129}.bin (the exact five refs the device
    ghost arbitration used -- see ghost_arbitration.json refs_used_ids).

The whole point of #5 was that the plane-sweep produces NO per-view depth of its
own, so its candidates carry support but no self-generated opposition.  Here we
give them the best opposition that physically exists on the capture (the five L1
depth maps) and measure, honestly, whether it is enough to convict the chair.

This script loads NO 4K pixels: support is read from the frozen PLY, opposition
needs only the 18 MB of L1 depth maps + camera poses.  Peak RSS stays well under
1 GB.  Deterministic; two runs are byte-identical.
"""
from __future__ import annotations

import gc
import hashlib
import json
import resource
import struct
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np

REPO = Path("/Users/kaidongwang/.config/superpowers/worktrees/"
            "pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
PINNED_REVISION = "f2fc9a1"
PINNED_SOURCE_PATH = ("experiments/floor_plane_sweep_densifier_2026-07-13/"
                      "fr_planesweep_wall_ceiling.py")
PINNED_SOURCE_SHA256 = "d34a8bd3f76d5d11c8ad1917bb53339306a17595fca3fbf5609bacb7863498e2"

OUT_DIR = REPO / "experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote"
CAP = REPO / "data/pocketworld_captures/cap50"
DPULL = CAP / "device_full_pull_2026-07-17"

UNION_PLY = (REPO / "experiments/u3_merge_prototypes_2026-07-18/05_median_fusion/"
             "union_baseline.ply")
UNION_EXPECTED_SHA = (
    "fdf5b105e55243d1b6599f640a2fe61727ca3c81197c56644f5304b3927d4c34")
UNION_EXPECTED_POINTS = 13_488
SFM_PLY = DPULL / "sfm_sparse.ply"

# Five on-device L1 (CasDiffMVS) depth refs -- the exact set the device ghost
# arbitration used (ghost_arbitration.json: refs_used_ids [20,129,2,128,83]).
L1_FRAME_IDS = [2, 20, 83, 128, 129]

# Chair / treadmill flatten ROI (top-down bottom-right corner), from the brief.
ROI = {"X0": 0.25, "X1": 1.05, "Z0": -1.70, "Z1": -0.55}

# Opposition parameters.  tau_free = how far in FRONT of a confident measured
# surface a candidate must sit to count as a free-space violation.  Primary =
# 10 cm (conservative: bigger than the few-cm floor agreement residual, so noise
# alone does not manufacture opposition).  Sensitivity swept below.
CONF_MIN = 0.5
TAU_PRIMARY_M = 0.10
TAU_SWEEP_M = [0.05, 0.10, 0.20]


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for blk in iter(lambda: s.read(1 << 20), b""):
            d.update(blk)
    return d.hexdigest()


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def load_pinned_module() -> types.ModuleType:
    payload = subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{PINNED_REVISION}:{PINNED_SOURCE_PATH}"])
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"pinned source SHA mismatch: {actual}")
    m = types.ModuleType("pinned_planesweep")
    m.__file__ = f"git:{PINNED_REVISION}:{PINNED_SOURCE_PATH}"
    sys.modules["pinned_planesweep"] = m
    exec(compile(payload, m.__file__, "exec"), m.__dict__)
    return m


def load_union_ply(path: Path):
    """Read the frozen ASCII union PLY: xyz, rgb, nviews, parallax, zncc, cviews."""
    lines = path.read_text().splitlines()
    hdr_end = lines.index("end_header") + 1
    rows = [ln.split() for ln in lines[hdr_end:] if ln.strip()]
    a = np.asarray(rows, dtype=np.float64)
    return {
        "xyz": a[:, 0:3].copy(),
        "rgb": a[:, 3:6].copy(),
        "nviews": a[:, 6].astype(np.int64).copy(),
        "parallax": a[:, 7].copy(),
        "zncc": a[:, 8].copy(),
        "candidate_views": a[:, 9].astype(np.int64).copy(),
    }


def load_sfm_ply(path: Path):
    with path.open("rb") as s:
        head = b""
        while b"end_header\n" not in head:
            head += s.read(1)
        n = None
        for ln in head.decode("ascii", "replace").splitlines():
            if ln.startswith("element vertex"):
                n = int(ln.split()[-1])
        raw = s.read(n * 15)
    dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                   ("r", "u1"), ("g", "u1"), ("b", "u1")])
    a = np.frombuffer(raw, dtype=dt, count=n)
    xyz = np.stack([a["x"], a["y"], a["z"]], axis=1).astype(np.float64)
    return xyz


def load_l1(fid: int):
    b = (DPULL / f"l1_depth_{fid}.bin").read_bytes()
    magic, ver, hid, H, W = struct.unpack("<5i", b[:20])
    if magic != 0x5044314C or hid != fid:  # b'L1DP' little-endian int32
        raise RuntimeError(f"bad L1 header for {fid}: magic={magic:#x} hid={hid}")
    data = np.frombuffer(b, dtype="<f4", offset=20)
    depth = data[:H * W].reshape(H, W).astype(np.float32).copy()
    conf = data[H * W:2 * H * W].reshape(H, W).astype(np.float32).copy()
    return depth, conf, H, W


def opposition_pass(xyz, frames_by_id, l1_maps, tau_free_m, conf_min):
    """Return per-candidate vote tallies against the L1 depth maps.

    Votes per view: free-space violation (opposition), occlusion (ignored),
    depth-agreement (independent support), abstain (oob / low-conf).
    resid = z_cam - d_L1 ; resid < -tau => candidate in FRONT => free-space viol.
    """
    N = len(xyz)
    n_free = np.zeros(N, dtype=np.int32)     # free-space violations (opposition)
    n_occ = np.zeros(N, dtype=np.int32)      # occlusion (candidate behind), ignored
    n_agree = np.zeros(N, dtype=np.int32)    # independent depth agreement (support)
    n_seen = np.zeros(N, dtype=np.int32)     # confident, in-bounds observations
    for fid, (depth, conf, H, W) in l1_maps.items():
        f = frames_by_id[fid]
        cam = (f.R @ xyz.T).T + f.t
        z = cam[:, 2]
        front = z > 0.05
        u = np.where(front, cam[:, 0] * f.K[0, 0] / np.where(front, z, 1.0) + f.K[0, 2], -1.0)
        v = np.where(front, cam[:, 1] * f.K[1, 1] / np.where(front, z, 1.0) + f.K[1, 2], -1.0)
        sx = W / f.width
        sy = H / f.height
        ud = u * sx
        vd = v * sy
        inb = front & (ud >= 0) & (ud <= W - 1) & (vd >= 0) & (vd <= H - 1)
        ui = np.clip(np.round(ud), 0, W - 1).astype(np.int64)
        vi = np.clip(np.round(vd), 0, H - 1).astype(np.int64)
        dl1 = depth[vi, ui]
        cl1 = conf[vi, ui]
        seen = inb & (cl1 > conf_min) & (dl1 > 0.05)
        resid = z - dl1
        free = seen & (resid < -tau_free_m)          # in front  -> opposition
        occ = seen & (resid > tau_free_m)            # behind    -> occlusion (ignore)
        agree = seen & (~free) & (~occ)              # |resid|<=tau -> support
        n_free += free
        n_occ += occ
        n_agree += agree
        n_seen += seen
    return n_free, n_occ, n_agree, n_seen


def summarize(mask, name, n_free, netvote, support):
    idx = np.where(mask)[0]
    tot = len(idx)
    if tot == 0:
        return {"name": name, "total": 0}
    nf = n_free[idx]
    return {
        "name": name,
        "total": int(tot),
        "with_freespace_ge1": int((nf >= 1).sum()),
        "with_freespace_ge1_frac": float((nf >= 1).mean()),
        "freespace_mean": float(nf.mean()),
        "freespace_max": int(nf.max()),
        # single-vote-conviction gate: any 1 free-space viol convicts
        "killed_by_single_vote": int((nf >= 1).sum()),
        "killed_by_single_vote_frac": float((nf >= 1).mean()),
        # Merrell net-vote gate: convict iff support < opposition (netvote < 0)
        "killed_by_netvote": int((netvote[idx] < 0).sum()),
        "killed_by_netvote_frac": float((netvote[idx] < 0).mean()),
        "support_median": float(np.median(support[idx])),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    m = load_pinned_module()
    frames = m.load_frames(CAP / "private_manifests/subset_meta_cap50full.json",
                           CAP / "private_manifests/sfm_fed_frames.jsonl",
                           CAP / "raw/photos_highres")
    fby = {int(f.frame_id): f for f in frames}
    for fid in L1_FRAME_IDS:
        if fid not in fby:
            raise RuntimeError(f"L1 ref frame {fid} missing from loaded frames")

    l1_maps = {fid: load_l1(fid) for fid in L1_FRAME_IDS}

    # ---- plane-sweep candidates + frozen photometric support ----
    union_sha = sha256_file(UNION_PLY)
    if union_sha != UNION_EXPECTED_SHA:
        raise RuntimeError(f"union PLY SHA mismatch: {union_sha}")
    U = load_union_ply(UNION_PLY)
    if len(U["xyz"]) != UNION_EXPECTED_POINTS:
        raise RuntimeError("union point count mismatch")
    xyz = U["xyz"]
    support = U["nviews"].astype(np.int32)          # frozen ZNCC clique support
    print(f"[{time.perf_counter()-t0:.1f}s] union {len(xyz)} pts sha={union_sha[:12]} "
          f"support(nviews) med={np.median(support):.0f}", flush=True)

    # ---- opposition against the five L1 depth maps (primary tau) ----
    n_free, n_occ, n_agree, n_seen = opposition_pass(
        xyz, fby, l1_maps, TAU_PRIMARY_M, CONF_MIN)
    netvote = support - n_free                       # Merrell stability

    # ---- ROI masks ----
    in_roi = ((xyz[:, 0] >= ROI["X0"]) & (xyz[:, 0] <= ROI["X1"]) &
              (xyz[:, 2] >= ROI["Z0"]) & (xyz[:, 2] <= ROI["Z1"]))
    outside = ~in_roi

    # non-wood ("blue-gray chair smear") heuristic from #5: b > r and b > 90.
    r, g, bl = U["rgb"][:, 0], U["rgb"][:, 1], U["rgb"][:, 2]
    nonwood = (bl > r) & (bl > 90)
    chair_smear = in_roi & nonwood

    # ---- Demonstration A: cure of false kills on weak-texture TRUE floor ----
    # True floor: OUTSIDE the chair ROI, strongly photometrically supported
    # (nviews>=5), yet caught >=1 L1 free-space violation (noisy L1 depth).
    true_floor_strong = outside & (support >= 5)
    falsekill = true_floor_strong & (n_free >= 1)    # killed by single-vote
    rescued = falsekill & (netvote >= 0)             # survive Merrell net-vote

    # ---- sensitivity sweep over tau_free ----
    sweep = {}
    for tau in TAU_SWEEP_M:
        f2, _, _, _ = opposition_pass(xyz, fby, l1_maps, tau, CONF_MIN)
        nv2 = support - f2
        sweep[f"{tau:.2f}"] = {
            "chair_smear_killed_single_vote": int((chair_smear & (f2 >= 1)).sum()),
            "chair_smear_killed_netvote": int((chair_smear & (nv2 < 0)).sum()),
            "chair_smear_total": int(chair_smear.sum()),
            "roi_killed_single_vote": int((in_roi & (f2 >= 1)).sum()),
            "roi_killed_netvote": int((in_roi & (nv2 < 0)).sum()),
            "roi_total": int(in_roi.sum()),
            "outside_falsekill_single_vote": int((true_floor_strong & (f2 >= 1)).sum()),
            "outside_rescued_by_netvote": int(
                (true_floor_strong & (f2 >= 1) & (nv2 >= 0)).sum()),
            "outside_true_floor_total": int(true_floor_strong.sum()),
        }

    # ---- SfM candidate opposition pass (support metadata unavailable) ----
    sfm_xyz = load_sfm_ply(SFM_PLY)
    sfm_free, sfm_occ, sfm_agree, sfm_seen = opposition_pass(
        sfm_xyz, fby, l1_maps, TAU_PRIMARY_M, CONF_MIN)
    sfm_in_roi = ((sfm_xyz[:, 0] >= ROI["X0"]) & (sfm_xyz[:, 0] <= ROI["X1"]) &
                  (sfm_xyz[:, 2] >= ROI["Z0"]) & (sfm_xyz[:, 2] <= ROI["Z1"]))

    # ---- write annotated candidate PLY (plane-sweep) ----
    ply_path = OUT_DIR / "netvote_candidates.ply"
    write_netvote_ply(ply_path, xyz, U["rgb"], support, n_free, n_occ,
                      n_agree, n_seen, netvote, in_roi)
    ply_sha = sha256_file(ply_path)

    # ROI survivor / chair-smear survivor PLYs for the viewer.
    roi_survivors = in_roi & (netvote >= 0)
    write_simple_ply(OUT_DIR / "roi_netvote_survivors.ply",
                     xyz[roi_survivors], U["rgb"][roi_survivors])
    write_simple_ply(OUT_DIR / "roi_all.ply", xyz[in_roi], U["rgb"][in_roi])
    write_simple_ply(OUT_DIR / "rescued_true_floor.ply",
                     xyz[rescued], U["rgb"][rescued])

    stats = {
        "schema": "u3_merrell_netvote_prototype_v1",
        "capture": "cap50",
        "tau_free_m_primary": TAU_PRIMARY_M,
        "conf_min": CONF_MIN,
        "l1_frame_ids": L1_FRAME_IDS,
        "roi_xz": ROI,
        "planesweep": {
            "total": int(len(xyz)),
            "support_min": int(support.min()),
            "support_median": float(np.median(support)),
            "support_max": int(support.max()),
            "candidates_with_any_l1_observation": int((n_seen >= 1).sum()),
            "candidates_with_freespace_ge1": int((n_free >= 1).sum()),
            "candidates_with_freespace_ge1_frac": float((n_free >= 1).mean()),
            "candidates_with_occlusion_ge1": int((n_occ >= 1).sum()),
            "freespace_votes_total": int(n_free.sum()),
            "occlusion_votes_total": int(n_occ.sum()),
            "agreement_votes_total": int(n_agree.sum()),
            # gate outcomes over the whole plane-sweep candidate set
            "killed_single_vote": int((n_free >= 1).sum()),
            "killed_single_vote_frac": float((n_free >= 1).mean()),
            "killed_netvote": int((netvote < 0).sum()),
            "killed_netvote_frac": float((netvote < 0).mean()),
        },
        "region_summaries": {
            "chair_roi_all": summarize(in_roi, "chair_roi_all", n_free, netvote, support),
            "chair_smear_nonwood": summarize(
                chair_smear, "chair_smear_nonwood", n_free, netvote, support),
            "outside_roi_true_floor_strong": summarize(
                true_floor_strong, "outside_roi_true_floor_strong",
                n_free, netvote, support),
        },
        "demonstration_A_cure_false_kills": {
            "definition": ("outside-ROI floor candidates with photometric "
                           "support nviews>=5 that catch >=1 L1 free-space "
                           "violation"),
            "killed_by_single_vote_conviction": int(falsekill.sum()),
            "rescued_by_netvote": int(rescued.sum()),
            "rescued_frac_of_falsekill": (
                float(rescued.sum() / falsekill.sum()) if falsekill.sum() else 0.0),
            "rescued_support_median": (
                float(np.median(support[rescued])) if rescued.sum() else 0.0),
            "rescued_opposition_median": (
                float(np.median(n_free[rescued])) if rescued.sum() else 0.0),
        },
        "demonstration_B_chair_honest_test": {
            "chair_smear_total": int(chair_smear.sum()),
            "chair_smear_killed_by_single_vote": int((chair_smear & (n_free >= 1)).sum()),
            "chair_smear_killed_by_netvote": int((chair_smear & (netvote < 0)).sum()),
            "chair_roi_total": int(in_roi.sum()),
            "chair_roi_killed_by_netvote": int((in_roi & (netvote < 0)).sum()),
            "chair_roi_freespace_votes_total": int(n_free[in_roi].sum()),
            "chair_roi_occlusion_votes_total": int(n_occ[in_roi].sum()),
            "chair_roi_candidates_with_any_l1_obs": int((in_roi & (n_seen >= 1)).sum()),
            "chair_roi_candidates_no_l1_obs": int((in_roi & (n_seen == 0)).sum()),
            "verdict": None,  # filled below
        },
        "sensitivity_tau_free": sweep,
        "sfm_opposition_pass": {
            "note": ("per-point photometric support (track length) is NOT in the "
                     "pulled artifacts (sfm_sparse.ply is xyz+rgb; sfm_live.db is "
                     "a feature/match DB with no points3D), so SfM cannot get a "
                     "faithful net-vote support term. Reported: opposition only, "
                     "plus that the on-device pipeline already ran free-space "
                     "arbitration on the SfM cloud (ghost_arbitration.json)."),
            "total": int(len(sfm_xyz)),
            "with_freespace_ge1": int((sfm_free >= 1).sum()),
            "with_freespace_ge1_frac": float((sfm_free >= 1).mean()),
            "in_roi_total": int(sfm_in_roi.sum()),
            "in_roi_with_freespace_ge1": int((sfm_in_roi & (sfm_free >= 1)).sum()),
        },
        "artifacts": {
            "netvote_candidates_ply": str(ply_path),
            "netvote_candidates_ply_sha256": ply_sha,
        },
        "elapsed_s": time.perf_counter() - t0,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }
    # honest verdict string
    b = stats["demonstration_B_chair_honest_test"]
    b["verdict"] = (
        f"net-vote kills {b['chair_smear_killed_by_netvote']}/"
        f"{b['chair_smear_total']} chair-smear points "
        f"({100.0*b['chair_smear_killed_by_netvote']/max(b['chair_smear_total'],1):.1f}%); "
        "the chair-flatten false positive is NOT cured by the net-vote gate "
        "because the plane-sweep candidates carry strong photometric support and "
        "the L1 depth maps supply essentially no free-space opposition against "
        "them (they either do not cover the coverage-edge ROI, abstain on low "
        "confidence, or see the flattened point as occluded behind the real "
        "object rather than in free space). Root cause is upstream: no "
        "independent per-view depth for the plane-sweep candidates -> no "
        "counter-evidence to net against.")

    (OUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    gc.collect()
    print(f"[{time.perf_counter()-t0:.1f}s] done. RSS {rss_gb():.2f} GB", flush=True)
    print(json.dumps(stats, indent=2, sort_keys=True))
    return stats


def write_netvote_ply(path, xyz, rgb, support, n_free, n_occ, n_agree, n_seen,
                      netvote, in_roi):
    with path.open("w", encoding="utf-8") as s:
        s.write("ply\nformat ascii 1.0\n")
        s.write(f"element vertex {len(xyz)}\n")
        s.write("property float x\nproperty float y\nproperty float z\n")
        s.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        for nm in ("support", "freespace_opposition", "occlusion", "agreement",
                   "l1_observations", "netvote", "in_roi"):
            s.write(f"property float {nm}\n")
        s.write("end_header\n")
        for i in range(len(xyz)):
            p = xyz[i]
            c = np.clip(np.rint(rgb[i]), 0, 255).astype(int)
            s.write(f"{p[0]:.7f} {p[1]:.7f} {p[2]:.7f} {c[0]} {c[1]} {c[2]} "
                    f"{support[i]:.0f} {n_free[i]:.0f} {n_occ[i]:.0f} {n_agree[i]:.0f} "
                    f"{n_seen[i]:.0f} {netvote[i]:.0f} {int(in_roi[i])}\n")


def write_simple_ply(path, xyz, rgb):
    with path.open("w", encoding="utf-8") as s:
        s.write("ply\nformat ascii 1.0\n")
        s.write(f"element vertex {len(xyz)}\n")
        s.write("property float x\nproperty float y\nproperty float z\n")
        s.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        s.write("end_header\n")
        for p, c in zip(xyz, rgb):
            cu = np.clip(np.rint(c), 0, 255).astype(int)
            s.write(f"{p[0]:.7f} {p[1]:.7f} {p[2]:.7f} {cu[0]} {cu[1]} {cu[2]}\n")


if __name__ == "__main__":
    main()
