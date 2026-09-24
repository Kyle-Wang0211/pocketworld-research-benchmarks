#!/usr/bin/env python3
"""Experiment L: per-depth-layer scale diagnosis on the worst window edges.

LASER (arXiv 2512.13680) claims inter-window scale error is NOT a single
scalar — it varies by depth layer (monocular scale ambiguity acts per layer).
If true for our pose-conditioned windows, the worst edges' overlap ratios
should differ systematically across depth bins; if false, per-window scalar
correction (component A) is sufficient and per-layer machinery is unnecessary.

For each requested edge w->w+1: pool the shared frames' per-pixel depth ratios
(both-conf-gated, same semantics as the chain measurement), bin them by the
window-w depth quantile (6 bins), and report per-bin median ratio + IQR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from expH_window_chain_fusion import load_windows  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--edges", default="9,14,15,22,35", help="comma list of edge start indices w (edge w->w+1)")
    parser.add_argument("--k", type=int, default=18)
    parser.add_argument("--stride", type=int, default=9)
    parser.add_argument("--bins", type=int, default=6)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    wins = load_windows(args.run_dir)
    n_shared = args.k - args.stride
    report = []
    for w in (int(v) for v in args.edges.split(",")):
        a, b = wins[w], wins[w + 1]
        ca = np.maximum(a["conf"] - 1.0, 0.0)
        cb = np.maximum(b["conf"] - 1.0, 0.0)
        ta, tb = ca.mean() * 0.5, cb.mean() * 0.5
        d_ref, ratios = [], []
        for s in range(n_shared):
            sa, sb = args.stride + s, s
            m = (ca[sa] >= ta) & (cb[sb] >= tb)
            if np.count_nonzero(m) < 500:
                continue
            d_ref.append(a["depth"][sa][m])
            ratios.append(a["depth"][sa][m] / np.maximum(b["depth"][sb][m], 1e-6))
        d_ref = np.concatenate(d_ref)
        ratios = np.concatenate(ratios)
        qs = np.quantile(d_ref, np.linspace(0, 1, args.bins + 1))
        rows = []
        for i in range(args.bins):
            sel = (d_ref >= qs[i]) & (d_ref < qs[i + 1] if i < args.bins - 1 else d_ref <= qs[i + 1])
            r = ratios[sel]
            rows.append(
                {
                    "depth_range_m": [round(float(qs[i]), 2), round(float(qs[i + 1]), 2)],
                    "median_ratio": round(float(np.median(r)), 4),
                    "iqr": [round(float(np.percentile(r, 25)), 4), round(float(np.percentile(r, 75)), 4)],
                    "pixels": int(r.size),
                }
            )
        meds = [row["median_ratio"] for row in rows]
        spread = (max(meds) - min(meds)) * 100
        overall = float(np.median(ratios))
        report.append({"edge": f"{w:03d}->{w + 1:03d}", "overall_median": round(overall, 4), "per_layer": rows, "layer_spread_pct": round(spread, 2)})
        print(f"edge {w:03d}->{w + 1:03d}: overall {overall:.4f}  各层中位 {meds}  层间散布 {spread:.1f}pp")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
