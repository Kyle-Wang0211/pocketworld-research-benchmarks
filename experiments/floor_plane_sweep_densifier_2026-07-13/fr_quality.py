#!/usr/bin/env python3
"""Adversarial quality audit of the merged floor rescue.
Reads per-point props from each band PLY and asks: does merging degrade quality?
LoFTR levers carry tri_angle/reproj/nview/floor_dist; plane-sweep carries zncc/parallax/ninlier."""
import numpy as np, fr_common as fc

def read_ply_ascii(path):
    lines = open(path).read().splitlines()
    hi = lines.index("end_header")
    props = [l.split()[-1] for l in lines[:hi] if l.startswith("property")]
    data = np.array([ln.split() for ln in lines[hi+1:] if ln.strip()], float)
    return data, props

def col(data, props, name):
    return data[:, props.index(name)] if name in props else None

def stats_loftr(tag, path):
    d, p = read_ply_ascii(path)
    ta = col(d, p, "tri_angle_deg"); rp = col(d, p, "max_reproj_px")
    nv = col(d, p, "nview"); fd = col(d, p, "floor_dist_m")
    print(f"{tag:22s} n={len(d):5d} | tri med={np.median(ta):5.2f} p10={np.percentile(ta,10):4.2f} "
          f"| reproj med={np.median(rp):4.2f} p90={np.percentile(rp,90):4.2f} "
          f"| tri>=2={np.mean(ta>=2)*100:5.1f}% reproj<3={np.mean(rp<3)*100:5.1f}% "
          f"| nview>=3={np.mean(nv>=3)*100:4.1f}% | |fd|mm med={np.median(np.abs(fd))*1000:4.1f}")
    return d, p

print("=== LoFTR levers (gate: reproj<3, tri>=2, MAGSAC/Sampson<3) ===")
dB, pB = stats_loftr("B_loftr_native1024", fc.FR + "/floor_rescue_D_band.ply")
dC, pC = stats_loftr("C_loftr_g4split",   fc.FR + "/floor_rescue_band_improved.ply")

# combined LoFTR union quality
def cols(d, p, name): return d[:, p.index(name)]
allta = np.concatenate([cols(dB,pB,"tri_angle_deg"), cols(dC,pC,"tri_angle_deg")])
allrp = np.concatenate([cols(dB,pB,"max_reproj_px"), cols(dC,pC,"max_reproj_px")])
allnv = np.concatenate([cols(dB,pB,"nview"), cols(dC,pC,"nview")])
print(f"\n{'B u C combined':22s} n={len(allta):5d} | tri med={np.median(allta):5.2f} "
      f"| reproj med={np.median(allrp):4.2f} p90={np.percentile(allrp,90):4.2f} "
      f"| tri>=2={np.mean(allta>=2)*100:5.1f}% reproj<3={np.mean(allrp<3)*100:5.1f}% nview>=3={np.mean(allnv>=3)*100:4.1f}%")
print(f"  baseline (1435) reference: tri med=11.31  reproj med=1.09  (all pass gate)")

print("\n=== plane-sweep A (gate: ZNCC>=0.70, >=3 consistent views, parallax>=5deg) ===")
for tag, f in [("A_planesweep_1cm", "floor_planesweep.ply"), ("A_planesweep_5mm", "floor_planesweep_5mm.ply")]:
    d, p = read_ply_ascii(fc.FR + "/" + f)
    z = col(d,p,"zncc_med"); pa = col(d,p,"parallax_deg"); ni = col(d,p,"ninlier")
    print(f"{tag:22s} n={len(d):5d} | ZNCC med={np.median(z):.3f} p10={np.percentile(z,10):.3f} "
          f"| parallax med={np.median(pa):5.1f} | ninlier med={np.median(ni):.0f} "
          f"| all ZNCC>=0.70={np.mean(z>=0.70)*100:.1f}% all parallax>=5={np.mean(pa>=5)*100:.1f}%")

# adversarial: how close to the reproj gate does each LoFTR lever sit? (near-gate fraction)
print("\n=== adversarial: near-gate crowding (reproj in [2.5,3.0) = borderline) ===")
for tag, d, p in [("B_native", dB, pB), ("C_g4", dC, pC)]:
    rp = cols(d,p,"max_reproj_px")
    print(f"{tag:10s} reproj>=2.5: {np.mean(rp>=2.5)*100:5.1f}%   >=2.0: {np.mean(rp>=2.0)*100:5.1f}%   median={np.median(rp):.2f}")
