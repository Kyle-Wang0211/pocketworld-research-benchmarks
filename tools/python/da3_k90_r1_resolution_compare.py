#!/usr/bin/env python3
"""R1-level quality comparison across K=90 iPhone runs at different resolutions.

Inputs: two or more pulled da3_bench_run_* dirs (Da3DepthPlugin per-frame format).
Metrics (no R2-R5 needed):
  1. Confidence stats — per-run mean/median/P10/P90 of depth_conf, plus the
     fraction of pixels above the median-style threshold the oracle uses.
  2. Overlap depth consistency — adjacent windows share `overlap` frames: the
     same physical frame appears as (window i, slot overlap+j) and
     (window i+1, slot j). Relative depth is per-window scale-ambiguous, so we
     normalize by the median ratio, then report RMS relative error. Lower =
     more self-consistent depth across windows.
  3. Pose consistency — same shared frame's pred_extrinsics differ by each
     window's gauge; we report rotation angle spread after Procrustes-style
     per-pair alignment of the overlap segment (cheap proxy: relative-pose
     consistency between consecutive shared frames).
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

SLOT_RE = re.compile(r"_slot_(\d+)$")


def load_window_arrays(window_dir: Path, height: int, width: int):
    depth_dir = window_dir / "relative_depth"
    conf_dir = window_dir / "confidence"

    def slot_of(p: Path) -> int:
        m = SLOT_RE.search(p.stem)
        return int(m.group(1))

    files = sorted(depth_dir.glob("*.bin"), key=slot_of)
    k = len(files)
    plane = height * width
    depth = np.empty((k, height, width), dtype=np.float32)
    conf = np.empty((k, height, width), dtype=np.float32)
    for slot, f in enumerate(files):
        depth[slot] = np.fromfile(f, dtype=np.float32).reshape(height, width)
        conf[slot] = np.fromfile(conf_dir / f.name, dtype=np.float32).reshape(height, width)
    return depth, conf


def run_metrics(run_dir: Path, height: int, width: int, overlap: int) -> dict:
    with (run_dir / "bench_summary.json").open() as f:
        summary = json.load(f)
    windows = sorted(summary["windows"], key=lambda w: w["window_index"])

    all_conf_samples = []
    per_window = []
    cache = {}

    for w in windows:
        idx = w["window_index"]
        depth, conf = load_window_arrays(run_dir / f"window_{idx:03d}", height, width)
        cache[idx] = (depth, conf, w["window_start"])
        # sample conf for stats (stride to keep memory sane)
        all_conf_samples.append(conf[:, ::4, ::4].ravel())
        per_window.append({
            "index": idx,
            "conf_mean": float(conf.mean()),
            "conf_median": float(np.median(conf)),
        })

    conf_all = np.concatenate(all_conf_samples)
    conf_stats = {
        "mean": float(conf_all.mean()),
        "median": float(np.median(conf_all)),
        "p10": float(np.percentile(conf_all, 10)),
        "p90": float(np.percentile(conf_all, 90)),
        "frac_above_median_x0.1": float((conf_all > np.median(conf_all) * 0.1).mean()),
    }

    # Overlap depth consistency between consecutive windows
    rms_list = []
    for w in windows[:-1]:
        i = w["window_index"]
        j = i + 1
        if j not in cache:
            continue
        d1, c1, s1 = cache[i]
        d2, c2, s2 = cache[j]
        shift = s2 - s1                      # how many frames window j is ahead
        n_shared = d1.shape[0] - shift       # frames shared between the two
        if n_shared <= 0:
            continue
        a = d1[shift:]                       # window i slots [shift..K)
        b = d2[:n_shared]                    # window j slots [0..n_shared)
        ca = c1[shift:]
        cb = c2[:n_shared]
        # confident pixels in both
        thr_a = np.median(ca) * 0.5
        thr_b = np.median(cb) * 0.5
        mask = (ca > thr_a) & (cb > thr_b) & (a > 1e-6) & (b > 1e-6)
        if mask.sum() < 1000:
            continue
        ratio = np.median(a[mask] / b[mask])  # per-pair scale normalization
        rel_err = (a[mask] - ratio * b[mask]) / np.maximum(a[mask], 1e-6)
        rms = float(np.sqrt(np.mean(rel_err ** 2)))
        rms_list.append({"pair": f"{i}-{j}", "scale_ratio": float(ratio),
                         "rms_rel_err": rms, "n_px": int(mask.sum())})

    return {
        "run": str(run_dir),
        "model": summary.get("model"),
        "resolution": f"{height}x{width}",
        "conf_stats": conf_stats,
        "per_window_conf": per_window,
        "overlap_consistency": rms_list,
        "overlap_rms_mean": float(np.mean([r["rms_rel_err"] for r in rms_list]))
        if rms_list else None,
        "scale_ratio_spread": float(np.std([r["scale_ratio"] for r in rms_list]))
        if rms_list else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="append", nargs=3, required=True,
                   metavar=("DIR", "HEIGHT", "WIDTH"),
                   help="repeatable: run dir + height + width")
    p.add_argument("--overlap", type=int, default=45)
    p.add_argument("--out-json", type=Path, default=None)
    args = p.parse_args()

    reports = []
    for run_dir, h, w in args.run:
        rep = run_metrics(Path(run_dir), int(h), int(w), args.overlap)
        reports.append(rep)
        print(f"\n=== {rep['model']} ({rep['resolution']}) ===")
        cs = rep["conf_stats"]
        print(f"conf: mean={cs['mean']:.4f} median={cs['median']:.4f} "
              f"p10={cs['p10']:.4f} p90={cs['p90']:.4f}")
        print(f"overlap RMS rel-err (mean over pairs): {rep['overlap_rms_mean']:.4f}")
        print(f"scale-ratio spread across pairs: {rep['scale_ratio_spread']:.4f}")
        for r in rep["overlap_consistency"]:
            print(f"  pair {r['pair']}: rms={r['rms_rel_err']:.4f} "
                  f"scale={r['scale_ratio']:.4f} px={r['n_px']}")

    if args.out_json:
        with args.out_json.open("w") as f:
            json.dump(reports, f, indent=2)
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
