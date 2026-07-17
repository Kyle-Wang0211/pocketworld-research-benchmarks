#!/usr/bin/env python3
"""Post-hoc decision-rule sweep over the already-scored off-plane competitors.

No re-scoring: reads depth_competition.jsonl and, for a grid of (margin,
offset-direction, view-dominance) rules, computes chair-FP kill rate vs clean-floor
retention. The question: does ANY operating point kill the chair false positives
without also holing genuine floor? Diagnostic only; selects no production threshold.
"""
import json
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent
rows = [json.loads(l) for l in (DIR / "depth_competition.jsonl").read_text().splitlines()]
roi_fp = [r for r in rows if r["population"] == "roi" and r["is_false_positive_color"]]
roi_wood = [r for r in rows if r["population"] == "roi" and not r["is_false_positive_color"]]
clean = [r for r in rows if r["population"] == "clean"]


def survives(r, margin, direction, viewdom):
    """direction: 'both'|'pos'|'neg' offsets considered as competitors."""
    cv, cn = r["floor_views"], r["floor_ncc"]
    for a in r["offsets"]:
        if a["ncc"] is None:
            continue
        o = a["offset_m"]
        if direction == "pos" and o < 0:
            continue
        if direction == "neg" and o > 0:
            continue
        # competitor beats floor -> floor NOT unique
        if viewdom:
            beats = not (cv >= a["views"] and cn >= a["ncc"] + margin)
        else:
            beats = not (cn >= a["ncc"] + margin)
        if beats:
            return False
    return True


def rate(rs, margin, direction, viewdom):
    if not rs:
        return 0.0
    s = sum(1 for r in rs if survives(r, margin, direction, viewdom))
    return s / len(rs)


print(f"{'rule':<34}{'FP_kill':>9}{'wood_ret':>10}{'clean_ret':>11}{'separation':>12}")
print("-" * 76)
results = []
for viewdom in (True, False):
    for direction in ("both", "pos"):
        for margin in (0.02, 0.05, 0.08, 0.10, 0.15, 0.20):
            fp_kill = 1.0 - rate(roi_fp, margin, direction, viewdom)
            wood_ret = rate(roi_wood, margin, direction, viewdom)
            clean_ret = rate(clean, margin, direction, viewdom)
            # separation = how well we kill chair while keeping clean floor
            sep = fp_kill * clean_ret
            tag = f"vd={int(viewdom)} {direction:<4} m={margin:.2f}"
            print(f"{tag:<34}{fp_kill*100:>8.1f}%{wood_ret*100:>9.1f}%"
                  f"{clean_ret*100:>10.1f}%{sep:>12.3f}")
            results.append({
                "viewdom": viewdom, "direction": direction, "margin": margin,
                "fp_kill_rate": fp_kill, "roi_wood_retention": wood_ret,
                "clean_floor_retention": clean_ret, "separation_product": sep,
            })

# margin distribution: how close does floor come to losing on clean floor?
def best_margin_over_all(r, direction):
    cn = r["floor_ncc"]
    diffs = []
    for a in r["offsets"]:
        if a["ncc"] is None:
            continue
        if direction == "pos" and a["offset_m"] < 0:
            continue
        diffs.append(cn - a["ncc"])
    return min(diffs) if diffs else None  # worst-case (smallest) floor advantage


clean_worst = np.array([m for r in clean if (m := best_margin_over_all(r, "both")) is not None])
wood_worst = np.array([m for r in roi_wood if (m := best_margin_over_all(r, "both")) is not None])
fp_worst = np.array([m for r in roi_fp if (m := best_margin_over_all(r, "both")) is not None])


def pct(a):
    return {f"p{k}": float(np.percentile(a, k)) for k in (10, 25, 50, 75, 90)} if len(a) else {}


analysis = {
    "schema": "u3_offplane_depth_competition_decision_sweep_v1",
    "diagnostic_only": True,
    "note": ("worst-case floor advantage = floor_ncc - max(competitor_ncc) over all "
             "16 offsets; if <= a margin the floor cell is holed. If clean-floor "
             "worst-case advantage is not clearly larger than chair-FP's, no single "
             "margin separates them."),
    "worst_case_floor_advantage_ncc": {
        "clean_floor_subsample": {"n": len(clean_worst), **pct(clean_worst),
                                  "frac_le_0.02": float(np.mean(clean_worst <= 0.02)) if len(clean_worst) else None,
                                  "frac_le_0.05": float(np.mean(clean_worst <= 0.05)) if len(clean_worst) else None},
        "roi_wood_floor": {"n": len(wood_worst), **pct(wood_worst),
                           "frac_le_0.02": float(np.mean(wood_worst <= 0.02)) if len(wood_worst) else None,
                           "frac_le_0.05": float(np.mean(wood_worst <= 0.05)) if len(wood_worst) else None},
        "roi_chair_fp": {"n": len(fp_worst), **pct(fp_worst),
                         "frac_le_0.02": float(np.mean(fp_worst <= 0.02)) if len(fp_worst) else None,
                         "frac_le_0.05": float(np.mean(fp_worst <= 0.05)) if len(fp_worst) else None},
    },
    "rule_sweep": results,
    "best_separation": max(results, key=lambda r: r["separation_product"]),
}
(DIR / "decision_sweep.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
print("\nworst-case floor advantage (floor_ncc - best competitor):")
for name, a in (("clean", clean_worst), ("roi_wood", wood_worst), ("roi_chair_fp", fp_worst)):
    print(f"  {name:<12} n={len(a):>4} p10={np.percentile(a,10):+.3f} med={np.median(a):+.3f} "
          f"p90={np.percentile(a,90):+.3f}  <=0.02:{np.mean(a<=0.02)*100:.0f}% <=0.05:{np.mean(a<=0.05)*100:.0f}%")
print("\nbest separation rule:", json.dumps(analysis["best_separation"]))
