#!/usr/bin/env python3.11
"""DR6: plot the stage-1 rounds cost curve (cap51 host replay)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DR6 = Path(__file__).resolve().parent
rows = json.loads((DR6 / "curve.json").read_text())
by = {r["arm"]: r for r in rows}
arms = ["cap1", "cap2", "cap3", "cap4", "cap5"]
x = [1, 2, 3, 4, 5]

fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))

ax = axes[0]
s1 = [by[a]["seg_stage1_ms"] / 1000 for a in arms]
s2 = [by[a]["seg_stage2_ms"] / 1000 for a in arms]
en = [by[a]["seg_enrich_ms"] / 1000 for a in arms]
fin = [by[a]["finalize_ms"] / 1000 for a in arms]
ax.plot(x, s1, "o-", label="stage1_ms (parallel window)")
ax.plot(x, s2, "s-", label="stage2_ms (serial)")
ax.plot(x, en, "^-", label="enrich_ms")
ax.plot(x, fin, "k*-", label="finalize_ms total")
ax.axhline(by["base"]["finalize_ms"] / 1000, color="gray", ls="--",
           label=f"base(unset) finalize {by['base']['finalize_ms']/1000:.1f}s")
ax.axhline(30.0, color="orange", ls=":", label="AUTO enrich floor 30 s")
ax.set_xlabel("AETHER_STAGE1_ROUNDS_CAP")
ax.set_ylabel("seconds (host M3 Pro)")
ax.set_title("cap51 host replay: time vs rounds cap")
ax.legend(fontsize=7)
ax.grid(alpha=0.3)

ax = axes[1]
pts = [by[a]["n_points"] for a in arms]
ax.plot(x, pts, "o-", color="tab:green")
ax.axhline(by["base"]["n_points"], color="gray", ls="--", label="base")
ax.set_xlabel("AETHER_STAGE1_ROUNDS_CAP")
ax.set_ylabel("n_points")
band = max(abs(p - by["base"]["n_points"]) for p in pts)
ax.set_title(f"points (max |delta| vs base = {band})")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[2]
th = [by[a]["floor_thickness_mm"] for a in arms]
rp = [by[a]["mean_reproj_px"] for a in arms]
ax.plot(x, th, "o-", color="tab:red", label="floor thickness mm (single-run: lottery)")
ax.axhline(by["base"]["floor_thickness_mm"], color="gray", ls="--", label="base thickness")
ax2 = ax.twinx()
ax2.plot(x, rp, "s--", color="tab:blue", label="mean reproj px")
ax2.set_ylabel("mean reproj px", color="tab:blue")
ax2.set_ylim(0.80, 0.85)
ax.set_xlabel("AETHER_STAGE1_ROUNDS_CAP")
ax.set_ylabel("floor thickness mm", color="tab:red")
ax.set_title("quality proxies vs rounds cap")
ax.legend(fontsize=7, loc="upper left")
ax.grid(alpha=0.3)

fig.tight_layout()
fig.savefig(DR6 / "rounds_curve.png", dpi=140)
print("WROTE", DR6 / "rounds_curve.png")
