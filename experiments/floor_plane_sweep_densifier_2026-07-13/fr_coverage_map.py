#!/usr/bin/env python3
"""Top-down (u,v) floor coverage map: SIFT vs LoFTR vs plane-sweep hole-fill.
Pure numpy + PIL. Reads the 1cm plane-sweep artifact."""
import numpy as np
from PIL import Image, ImageDraw
import fr_common as fc
from fr_planesweep import read_ply_xyz, to_uv  # reuse loaders/basis

FR = fc.FR
prod = to_uv(read_ply_xyz(FR + "/production_floor.ply"))
loftr = to_uv(read_ply_xyz(FR + "/floor_rescue_band.ply"))
ps = to_uv(read_ply_xyz(FR + "/floor_planesweep_1cm.ply"))

allpts = np.vstack([prod, loftr, ps])
amin, bmin = allpts.min(0) - 0.05
amax, bmax = allpts.max(0) + 0.05
PPM = 220  # px per meter
W = int((amax - amin) * PPM); H = int((bmax - bmin) * PPM)
def px(uv):
    x = (uv[:, 0] - amin) * PPM
    y = (uv[:, 1] - bmin) * PPM
    return np.stack([x, y], -1)

img = Image.new("RGB", (W, H), (18, 18, 22))
d = ImageDraw.Draw(img)
# 5cm cell grid faint
for a in np.arange(amin, amax, 0.05):
    x = (a - amin) * PPM; d.line([(x, 0), (x, H)], fill=(32, 32, 38))
for b in np.arange(bmin, bmax, 0.05):
    y = (b - bmin) * PPM; d.line([(0, y), (W, y)], fill=(32, 32, 38))

def dots(uv, color, r=1):
    for x, y in px(uv):
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

# SIFT (gray), LoFTR (cyan), plane-sweep (green)
dots(prod, (150, 150, 155), 1)
dots(loftr, (60, 180, 220), 1)
dots(ps, (70, 220, 90), 1)

# legend
d.rectangle([8, 8, 250, 92], fill=(0, 0, 0))
d.ellipse([16, 18, 22, 24], fill=(150, 150, 155)); d.text((30, 15), "SIFT floor (production)", fill=(220, 220, 220))
d.ellipse([16, 40, 22, 46], fill=(60, 180, 220)); d.text((30, 37), "LoFTR rescue", fill=(220, 220, 220))
d.ellipse([16, 62, 22, 68], fill=(70, 220, 90)); d.text((30, 59), "plane-sweep (this lever)", fill=(220, 220, 220))
img.save(FR + "/overlay_topdown_coverage.png")
print("wrote overlay_topdown_coverage.png", (W, H))
