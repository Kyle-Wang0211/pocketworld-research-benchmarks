#!/usr/bin/env python3.11
# E17 L2 preview simulation — display-only semantics.
# Delivered PLY is NEVER modified; we only produce a *preview visual effect* PLY
# (hidden points removed from the DISPLAY artifact) to simulate the render gate.
# Rule (verbatim from lib/capture/ghost_view_filter.dart):
#   hidden = band15 AND NOT rescued   (band15 = bit1, rescued = bit5)
import hashlib, json, struct, sys
from pathlib import Path
import numpy as np

ROOT = Path("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
DATA = ROOT / "data/pocketworld_captures"
OUT = ROOT / "experiments/rs_replication_exec_2026-07-19/E17_l2_preview_sim"
OUT.mkdir(parents=True, exist_ok=True)

BIT_IN_REGION, BIT_BAND15, BIT_CELL_GHOST, BIT_IN_CLEAN, BIT_BAND10, BIT_RESCUED = 1,2,4,8,16,32

def sha(p: Path):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()

def load_ply(p: Path):
    data = p.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    header = data[:end].decode()
    n = int([l for l in header.splitlines() if l.startswith("element vertex")][0].split()[-1])
    assert "binary_little_endian" in header
    rec = np.frombuffer(data[end:end + n*15], dtype=np.dtype([("xyz","<f4",3),("rgb","u1",3)]))
    assert len(rec) == n
    return rec, header

def write_ply(p: Path, rec, comment):
    n = len(rec)
    hdr = ("ply\nformat binary_little_endian 1.0\n"
           f"comment {comment}\n"
           f"element vertex {n}\n"
           "property float x\nproperty float y\nproperty float z\n"
           "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    with open(p, "wb") as f:
        f.write(hdr.encode())
        f.write(rec.tobytes())

results = {}
for cap in ("cap50", "cap51"):
    d = DATA / cap / "device_full_pull_2026-07-17"
    ply, header = load_ply(d / "sfm_sparse.ply")
    n = len(ply)
    meta = json.loads((d / "ghost_mask.json").read_text())
    native = np.frombuffer((d / "ghost_mask.bin").read_bytes(), dtype=np.uint8)
    view = np.frombuffer((d / "ghost_view_mask.bin").read_bytes(), dtype=np.uint8)

    r = {"cap": cap, "delivered_ply_points": n,
         "native_mask_len": len(native), "view_mask_len": len(view),
         "aligned_view_mask": len(view) == n,
         "json_n_points": meta["n_points"], "json_n_band15": meta["n_band15"]}

    # native mask cross-check vs json
    r["native_band15"] = int(np.count_nonzero(native & BIT_BAND15))
    r["native_rescued_bit5"] = int(np.count_nonzero(native & BIT_RESCUED))

    assert len(view) == n, f"{cap}: view mask misaligned"
    band15 = (view & BIT_BAND15) != 0
    rescued = (view & BIT_RESCUED) != 0
    hidden = band15 & ~rescued
    r["view_band15"] = int(band15.sum())
    r["view_rescued_bit5"] = int(rescued.sum())
    r["hidden"] = int(hidden.sum())
    r["hidden_pct_of_total"] = round(100.0 * hidden.sum() / n, 3)
    r["band15_hide_ratio"] = round(100.0 * hidden.sum() / max(1, band15.sum()), 3)
    r["shown"] = int(n - hidden.sum())
    r["view_in_region"] = int(np.count_nonzero(view & BIT_IN_REGION))
    r["view_cell_ghost"] = int(np.count_nonzero(view & BIT_CELL_GHOST))
    r["view_band10"] = int(np.count_nonzero(view & BIT_BAND10))

    # production plane ruler (certified plane from ghost_mask.json)
    pn = np.array(meta["plane_n"]); pd = float(meta["plane_d"])
    xyz = ply["xyz"].astype(np.float64)
    sd = xyz @ pn + pd  # signed distance; floor at 0
    # sign sanity: median sd of in-region points should be ~0
    r["sd_median_in_region"] = round(float(np.median(sd[(view & BIT_IN_REGION) != 0])), 5) if r["view_in_region"] else None
    r["sd_median_all"] = round(float(np.median(sd)), 5)

    slab = 0.015
    near_floor = np.abs(sd) <= slab
    r["true_floor_points_abs_sd_le_1p5cm"] = int(near_floor.sum())
    r["mishidden_true_floor"] = int((hidden & near_floor).sum())
    r["mishide_rate_pct_of_true_floor"] = round(100.0 * (hidden & near_floor).sum() / max(1, near_floor.sum()), 4)
    r["hidden_below_floor"] = int((hidden & (sd < -slab)).sum())
    r["hidden_above_slab"] = int((hidden & (sd > slab)).sum())
    hid_sd = sd[hidden]
    if len(hid_sd):
        r["hidden_sd_cm"] = {"min": round(hid_sd.min()*100,2), "p50": round(float(np.median(hid_sd))*100,2),
                             "max": round(hid_sd.max()*100,2)}

    # preview visual-effect PLY (display simulation only; delivery stays full)
    prev = OUT / f"{cap}_l2on_preview.ply"
    write_ply(prev, ply[~hidden],
              f"E17 L2 preview SIMULATION (display-only visual effect; delivered PLY stays FULL). hidden=band15&~rescued removed from DISPLAY copy. source={cap} device_full_pull_2026-07-17")
    # full baseline copy for same-gauge compare
    full = OUT / f"{cap}_full_off.ply"
    full.write_bytes((d / "sfm_sparse.ply").read_bytes())
    r["files"] = {
        f"{cap}_l2on_preview.ply": sha(prev),
        f"{cap}_full_off.ply": sha(full),
        "source_sfm_sparse.ply": sha(d / "sfm_sparse.ply"),
        "source_ghost_mask.bin": sha(d / "ghost_mask.bin"),
        "source_ghost_view_mask.bin": sha(d / "ghost_view_mask.bin"),
    }
    np.save(OUT / f"{cap}_sd.npy", sd)
    np.save(OUT / f"{cap}_hidden.npy", hidden)
    results[cap] = r
    print(json.dumps(r, indent=1, ensure_ascii=False))

(OUT / "e17_metrics.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
print("METRICS ->", OUT / "e17_metrics.json")
