#!/usr/bin/env python3.11
"""Build source-colored overlay PLY + U3 observation-site candidate list + SHA-256 manifest.
Reads only from 06_glomap_alias/ outputs + production cloud. Writes only into 06_glomap_alias/."""
import numpy as np, json, os, hashlib, struct

OUT="/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias"
D="/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap50/"
CX=(0.25,1.05); CZ=(-1.70,-0.55)

xyz=np.load(D+"sfm/sfm_sparse_metric.npz")['xyz'].astype(np.float64)
rgb=np.load(D+"sfm/sfm_sparse_metric.npz")['rgb']
gm=json.load(open(D+"device_full_pull_2026-07-17/ghost_mask.json"))
n=np.array(gm['plane_n']); pd=gm['plane_d']

al=np.genfromtxt(os.path.join(OUT,'alias_points.csv'),delimiter=',',names=True)
A=np.stack([al['X'],al['Y'],al['Z']],1)
roi=al['in_chair_roi'].astype(bool)
sd=A@n+pd
band15=np.abs(sd)<0.15

# ---- overlay PLY: production cloud dimmed gray + alias points colored by source category ----
# production: subsample-free (full delivery) but dim gray so alias pops
def write_ply(path, pts, cols):
    m=np.all(np.isfinite(pts),1)
    pts=pts[m]; cols=cols[m]
    with open(path,'w') as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for p,c in zip(pts,cols):
            f.write(f"{p[0]:.5f} {p[1]:.5f} {p[2]:.5f} {int(c[0])} {int(c[1])} {int(c[2])}\n")

prod_col=np.full((len(xyz),3),90,np.uint8)  # dim gray
# color: RED = alias in chair ROI, ORANGE = alias in floor band elsewhere, YELLOW = other alias
acol=np.zeros((len(A),3),np.uint8)
for i in range(len(A)):
    if roi[i]:               acol[i]=(255,20,20)     # chair-ROI alias (site candidate, high priority)
    elif band15[i]:          acol[i]=(255,140,0)     # floor-band alias elsewhere
    else:                    acol[i]=(255,230,0)     # other alias
allpts=np.vstack([xyz,A])
allcol=np.vstack([prod_col,acol])
write_ply(os.path.join(OUT,"overlay_cloud_alias.ply"), allpts, allcol)

# ---- U3 observation-site candidate list ----
alias_tracks=[json.loads(l) for l in open(os.path.join(OUT,"alias_tracks.jsonl"))]
# align by row order (csv rows follow alias_track_recs order == jsonl order)
site=[]
for i,t in enumerate(alias_tracks):
    X=A[i].tolist()
    site.append({
      "track_root": t["track_root"],
      "xyz": [round(v,4) for v in X],
      "n_obs": t["n_obs"],
      "n_images": t["n_images"],
      "dup_source_images": {k:v for k,v in t["dup_images"].items()},  # image_id -> colliding feature idxs
      "spread_m": round(float(al['spread_m'][i]),4),
      "in_chair_roi": bool(roi[i]),
      "in_floor_band15": bool(band15[i]),
      "signed_dist_floor_m": round(float(sd[i]),4),
      # U3 policy: DO NOT drop; mark for pre-birth arbitration. Priority by ROI+support.
      "u3_action": "mark_observation_site_candidate",
      "priority": ("high" if roi[i] else ("mid" if band15[i] else "low")),
      "rationale": "same-image multi-feature GLOMAP collision (repeated-texture/alias); stock GLOMAP drops whole track, U3 preserves as site id for pre-birth arbitration"
    })
with open(os.path.join(OUT,"u3_site_candidates.jsonl"),"w") as f:
    for s in site: f.write(json.dumps(s)+"\n")

# ---- refresh summary with spatial stats ----
summ=json.load(open(os.path.join(OUT,"tracks_summary.json")))
summ["spatial"]={
  "prod_frac_in_chair_roi": round(float(((xyz[:,0]>=CX[0])&(xyz[:,0]<=CX[1])&(xyz[:,2]>=CZ[0])&(xyz[:,2]<=CZ[1])).mean()),4),
  "alias_frac_in_chair_roi": round(float(roi.mean()),4),
  "chair_roi_enrichment_x": round(float(roi.mean()/((xyz[:,0]>=CX[0])&(xyz[:,0]<=CX[1])&(xyz[:,2]>=CZ[0])&(xyz[:,2]<=CZ[1])).mean()),2),
  "roi_binomial_z": 12.1,
  "alias_nn_to_prod_cloud_median_m": 0.0146,
  "alias_nn_frac_within_5cm": 0.885,
  "prod_floor_band15_frac": round(float((np.abs(xyz@n+pd)<0.15).mean()),4),
  "alias_floor_band15_frac_all": round(float(band15.mean()),4),
  "alias_roi_floor_band15_frac": round(float(band15[roi].mean()),4),
  "alias_nonroi_floor_band15_frac": round(float(band15[~roi].mean()),4),
  "alias_roi_spread_median_m": round(float(np.nanmedian(al['spread_m'][roi])),4),
  "alias_nonroi_spread_median_m": round(float(np.nanmedian(al['spread_m'][~roi])),4),
}
summ["honest_verdict"]=(
  "Alias is RARE globally (243 tracks = 0.25% of 96,595 tracks) and does NOT explain the ghost "
  "layer or double-wall as a whole (global alias floor-band rate 11.9% is BELOW the 16.1% cloud "
  "base rate). BUT alias is strongly spatially enriched in the chair squash ROI: 3.7x (28% vs 7.5%, "
  "z=12.1), and those ROI aliases are tightly triangulated (spread 0.016m) and sit in the floor band "
  "(23.5% vs 7.4% elsewhere) -> consistent with repeated-texture chair points collapsing onto a "
  "second/duplicated site. Alias is therefore a WEAK-VOLUME but SPATIALLY-SPECIFIC birth-time signal: "
  "it flags the chair ROI as an observation-site needing pre-birth arbitration, which is exactly the "
  "region #5 showed downstream free-space/opposition rules cannot kill."
)
json.dump(summ, open(os.path.join(OUT,"tracks_summary.json"),"w"), indent=2)

# ---- SHA-256 manifest ----
man={}
for fn in sorted(os.listdir(OUT)):
    p=os.path.join(OUT,fn)
    if fn=="manifest_sha256.json" or not os.path.isfile(p): continue
    h=hashlib.sha256(open(p,'rb').read()).hexdigest()
    man[fn]={"sha256":h,"bytes":os.path.getsize(p)}
json.dump(man, open(os.path.join(OUT,"manifest_sha256.json"),"w"), indent=2)
print(json.dumps(man,indent=2))
print("site_candidates:",len(site),"overlay pts:",len(allpts))
print("DONE")
