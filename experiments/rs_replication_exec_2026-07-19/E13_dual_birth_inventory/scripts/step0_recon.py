#!/usr/bin/env python3.11
"""E13 step0 — data recon & ruler verification (read-only).

1. Parse off-baseline models; verify track<->image cross references.
2. Cross-check images.bin 2D coords vs sfm_live.db keypoints (bit-identity).
3. Count bit-identical (x,y) alias sites per frame (DSP-SIFT variant aliasing).
4. Re-derive E12 raw production-frame rulers on off_r1/r2/r3 clouds and match
   the banked numbers in E12 analysis/raw_frame_forensics.json bit-for-bit.
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import (D, E9_RUNS, OFF_RUN, DB_PATH, load_db_keypoints, load_plane,
                     read_cameras_bin, read_images_bin_full, read_points3d_bin_full, read_ply)

E12_RAW = f"{D}/experiments/rs_replication_exec_2026-07-19/E12_stage2_fine_knife/analysis/raw_frame_forensics.json"


def raw_rulers(xyz, pn, pd):
    fh = xyz @ pn + pd
    cover_pts = xyz[np.abs(fh) <= 0.03]
    cover = len(set(zip(np.floor(cover_pts[:, 0] / 0.02).astype(np.int64),
                        np.floor(cover_pts[:, 2] / 0.02).astype(np.int64))))
    return {
        "n": int(len(xyz)),
        "true_floor_peak": int(((fh >= -0.0075) & (fh < 0.0125)).sum()),
        "ghost_band": int(((fh >= -0.045) & (fh < -0.020)).sum()),
        "mid_fat": int(((fh >= -0.045) & (fh < -0.010)).sum()),
        "above_6095": int(((fh >= 0.060) & (fh < 0.095)).sum()),
        "below_m10": int((fh < -0.100).sum()),
        "cover_raw_2cm": int(cover),
    }


def main():
    banked = json.load(open(E12_RAW))
    for cap in ("cap51", "cap50"):
        run = OFF_RUN[cap]
        print(f"== {cap} off run: {run}")
        ids, xyz, rgb, err, tracks = read_points3d_bin_full(f"{run}/points3D.bin")
        images = read_images_bin_full(f"{run}/images.bin")
        cams = read_cameras_bin(f"{run}/cameras.bin")
        print(f"  points3D: n={len(ids)}  track_len sum={sum(len(t) for t in tracks)} "
              f"median={int(np.median([len(t) for t in tracks]))}")
        print(f"  images.bin: n_reg={len(images)}  cameras: {[(c['model_id'], c['width'], c['height'], np.round(c['params'],2).tolist()) for c in cams.values()]}")

        # --- cross-reference integrity: every track obs resolves & back-refs
        id2row = {int(p): i for i, p in enumerate(ids)}
        n_obs = 0
        n_resolve = 0
        n_backref = 0
        for i, tr in enumerate(tracks):
            pid = int(ids[i])
            for iid, k in tr:
                n_obs += 1
                im = images.get(int(iid))
                if im is None or k >= len(im["p3d_ids"]):
                    continue
                n_resolve += 1
                if int(im["p3d_ids"][k]) == pid:
                    n_backref += 1
        print(f"  obs coverage: total={n_obs} resolve_xy={n_resolve} ({100*n_resolve/n_obs:.2f}%) "
              f"backref_ok={n_backref} ({100*n_backref/n_obs:.2f}%)")

        # --- db keypoints bit-identity vs images.bin
        kps = load_db_keypoints(DB_PATH[cap])
        n_img_match = 0
        n_img_tot = 0
        mism = []
        for iid, im in images.items():
            n_img_tot += 1
            k = kps.get(iid)
            if k is None:
                mism.append((iid, "no-db-row"))
                continue
            if len(k) != len(im["xys"]):
                mism.append((iid, f"count {len(k)} vs {len(im['xys'])}"))
                continue
            if np.array_equal(k.astype(np.float64), im["xys"]):
                n_img_match += 1
            else:
                d = np.abs(k.astype(np.float64) - im["xys"]).max()
                mism.append((iid, f"maxdiff {d:.6f}"))
        print(f"  db-vs-images.bin xy bit-identity: {n_img_match}/{n_img_tot} frames exact; mismatches: {mism[:5]}")

        # --- bit-identical alias sites inside each frame (on float32 db coords)
        tot_kp = 0
        tot_sites = 0
        tot_alias_kp = 0
        max_group = 0
        for iid, k in kps.items():
            v = k.view(np.uint32)  # bit patterns
            key = v[:, 0].astype(np.uint64) << np.uint64(32) | v[:, 1].astype(np.uint64)
            uq, cnt = np.unique(key, return_counts=True)
            tot_kp += len(k)
            tot_sites += len(uq)
            tot_alias_kp += int((cnt[cnt > 1]).sum())
            max_group = max(max_group, int(cnt.max()))
        print(f"  alias sites: keypoints={tot_kp} unique_xy_sites={tot_sites} "
              f"kp_in_multi_variant_sites={tot_alias_kp} ({100*tot_alias_kp/tot_kp:.1f}%) max_variants={max_group}")

        # --- ruler verification on off x3 replay_finalize.ply
        pn, pd = load_plane(cap)
        for r in ("off_r1", "off_r2", "off_r3"):
            ply = f"{E9_RUNS}/{cap}_{r}/replay_finalize.ply"
            pxyz, _ = read_ply(ply)
            mine = raw_rulers(pxyz, pn, pd)
            ref = banked[cap][r]
            ok = all(mine[k] == ref[k] for k in mine)
            print(f"  ruler {r}: {'MATCH' if ok else 'MISMATCH'} mine={mine}" + ("" if ok else f" ref={ref}"))

        # --- points3D xyz vs replay_finalize.ply xyz identity (row order)
        pxyz, _ = read_ply(f"{run}/replay_finalize.ply")
        if len(pxyz) == len(xyz):
            d = np.abs(pxyz - xyz).max()
            print(f"  points3D.bin vs replay_finalize.ply: same n={len(xyz)}, max|dxyz|={d:.2e} (f32 quantization expected)")
        else:
            print(f"  points3D.bin n={len(xyz)} vs ply n={len(pxyz)} — ORDER/SET MISMATCH")


if __name__ == "__main__":
    main()
