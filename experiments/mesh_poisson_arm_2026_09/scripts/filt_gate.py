#!/usr/bin/env python3
"""Gate on DepthMapFiltering: it must actually have had neighbour views to compare against.

Seen on 2026-09-17: one run of aliceVision_depthMapFiltering returned from "Precomputing groups" in 0.012 s having
found no nearest cameras, and silently deleted ~90% of every depth map (the same command rerun took 36 s and kept
everything). Nothing in its exit code or log said so. Compare the kept depth counts against the input.
  filt_gate.py <depth_dir> <filt_dir> [min_kept_fraction=0.30]"""
import sys, glob, os, OpenEXR
DEPTH, FILT = sys.argv[1], sys.argv[2]
MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30
def total(d):
    n = 0; files = sorted(glob.glob(f"{d}/*_depthMap.exr"))
    for p in files:
        with OpenEXR.File(p) as f:
            h = f.header()
            n += int(h.get("AliceVision:nbDepthValues", 0))
    return n, len(files)
a, na = total(DEPTH); b, nb = total(FILT)
if na == 0 or nb == 0: raise SystemExit(f"GATE FAIL: {na} input maps, {nb} filtered maps")
if nb != na: raise SystemExit(f"GATE FAIL: {na} input maps but {nb} filtered maps")
frac = b / a if a else 0
print(f"depth values: input {a:,} -> filtered {b:,} ({100*frac:.1f}% kept, {na} views)")
if frac < MIN:
    raise SystemExit(f"GATE FAIL: only {100*frac:.1f}% of depth values survived filtering (< {100*MIN:.0f}%). "
                     "The usual cause is that findNearestCamsFromLandmarks found no neighbours, which the tool "
                     "does not report as an error.")
print("GATE PASS")
