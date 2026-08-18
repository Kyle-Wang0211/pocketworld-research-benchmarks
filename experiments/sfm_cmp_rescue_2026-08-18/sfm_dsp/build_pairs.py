"""Build a COLMAP match-pair list from ARKit poses: each image x its K nearest
neighbours by camera center. Replaces exhaustive (85k pairs) with ~5k prior-guided
pairs -> matching minutes not ~hour. This is the product-realistic path (ARKit
poses as prior)."""
import json, numpy as np
from pathlib import Path
ROOT = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks")
MAN = ROOT/"data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json"
K = 25
man = json.load(open(MAN))["frames"]
names, cen = [], []
for f in man:
    e = np.array(f["cameraExtrinsic4x4"], float).reshape(4, 4)   # cam->world; center = translation col
    names.append(Path(f["jpegPath"]).name); cen.append(e[:3, 3])
cen = np.array(cen)
pairs = set()
for i in range(len(names)):
    d = np.linalg.norm(cen - cen[i], axis=1); idx = np.argsort(d)[1:K+1]
    for j in idx:
        pairs.add((min(i, j), max(i, j)))
out = Path(__file__).resolve().parent/"pairs.txt"
with open(out, "w") as fo:
    for i, j in sorted(pairs):
        fo.write(f"{names[i]} {names[j]}\n")
print(f"{len(names)} images -> {len(pairs)} prior pairs (K={K}) vs exhaustive {len(names)*(len(names)-1)//2}")
