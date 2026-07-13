#!/usr/bin/env python3
"""True-color top-down render of the MAXED merged floor rescue (plane-sweep 1cm + LoFTR B + C).
Colorize production-faithfully: project each 3D point into the floor frames it is visible in
(cheirality + in-bounds), sample HIGHRES bilinear at px*highres_scale-0.5, aggregate across
observations (median = occlusion-robust variant of production's cross-obs average), round.
Output: overlay_floor_maxed.png  (LEFT = SIFT only | RIGHT = SIFT + maxed rescue)."""
import os, json, struct, numpy as np
from PIL import Image
import fr_common as fc

FR = fc.FR
Image.MAX_IMAGE_PIXELS = None

def read_ply_ascii_xyz(path):
    lines = open(path).read().splitlines()
    hi = lines.index("end_header")
    data = np.array([ln.split()[:3] for ln in lines[hi+1:] if ln.strip()], float)
    return data

def read_ply_binary_rgb(path):
    buf = open(path, "rb").read()
    hdr = buf.split(b"end_header\n", 1)[0]
    nv = int([l for l in hdr.splitlines() if l.startswith(b"element vertex")][0].split()[-1])
    body = buf.split(b"end_header\n", 1)[1]
    xyz = np.zeros((nv, 3)); rgb = np.zeros((nv, 3), np.uint8)
    for i in range(nv):
        xyz[i] = struct.unpack_from("<fff", body, i*15)
        rgb[i] = struct.unpack_from("<BBB", body, i*15+12)
    return xyz, rgb

# ---- merged rescue points (plane-sweep 1cm recommended + LoFTR B native + C g4) ----
A = read_ply_ascii_xyz(FR + "/floor_planesweep.ply")          # 12672
B = read_ply_ascii_xyz(FR + "/floor_rescue_D_band.ply")       # 2350
C = read_ply_ascii_xyz(FR + "/floor_rescue_band_improved.ply")# 3480
# in-plane basis for a light exact-dup removal
n = fc.PLANE_N.copy(); a0 = np.array([1.,0,0])
if abs(n@a0)>0.9: a0=np.array([0,0,1.])
u = a0-(a0@n)*n; u/=np.linalg.norm(u); v=np.cross(n,u)
allp = np.vstack([A, B, C])
uv = np.stack([allp@u, allp@v],1)
keys = np.floor(uv/0.004).astype(np.int64)   # 4mm in-plane dedup (drop exact pile-ups)
_, idx = np.unique(keys, axis=0, return_index=True)
pts = allp[np.sort(idx)]
print(f"merged rescue pts: A={len(A)} B={len(B)} C={len(C)} -> dedup4mm={len(pts)}")

# ---- production-faithful colorize by reprojection into floor frames ----
FIDS = [f for f in fc.FLOOR_IDS if f in fc.POSES]
N = len(pts)
samp = np.full((N, len(FIDS), 3), np.nan, np.float32)
def bilinear_batch(img, fx, fy, mask):
    h, w = img.shape[:2]
    out = np.full((len(fx), 3), np.nan, np.float32)
    x0 = np.floor(fx).astype(int); y0 = np.floor(fy).astype(int)
    ok = mask & (x0>=0)&(y0>=0)&(x0<w-1)&(y0<h-1)
    xi=x0[ok]; yi=y0[ok]; dx=(fx[ok]-xi)[:,None]; dy=(fy[ok]-yi)[:,None]
    c00=img[yi,xi]; c01=img[yi,xi+1]; c10=img[yi+1,xi]; c11=img[yi+1,xi+1]
    out[ok]=(1-dx)*(1-dy)*c00+dx*(1-dy)*c01+(1-dx)*dy*c10+dx*dy*c11
    return out
for fi, fid in enumerate(FIDS):
    p = fc.POSES[fid]
    ip = p.get("img_highres"); scale = p.get("highres_scale", 1.0)
    if not (ip and os.path.exists(ip)): ip = p["img_work"]; scale = 1.0
    img = np.asarray(Image.open(ip).convert("RGB"), np.float32)
    Xc = (fc.R_of(fid) @ pts.T).T + fc.t_of(fid)   # cam coords
    z = Xc[:,2]
    uvh = (fc.K_of(fid) @ Xc.T).T
    xw = uvh[:,0]/uvh[:,2]; yw = uvh[:,1]/uvh[:,2]
    fx = xw*scale - 0.5; fy = yw*scale - 0.5
    cheiro = (z > fc.DEPTH_MIN) & (z < fc.DEPTH_MAX)
    samp[:, fi, :] = bilinear_batch(img, fx, fy, cheiro)
    del img
# median across observations (robust to occluders), round
valid = ~np.all(np.isnan(samp).all(2), 1)
rgb = np.zeros((N,3), np.uint8)
med = np.nanmedian(samp, axis=1)              # (N,3)
good = ~np.isnan(med).any(1)
rgb[good] = np.round(med[good]).clip(0,255).astype(np.uint8)
pts = pts[good]; rgb = rgb[good]
print(f"colorized {good.sum()}/{N} merged rescue points (median over floor-frame reprojections)")

# ---- SIFT reference ----
sxyz, srgb = read_ply_binary_rgb(FR + "/production_floor.ply")

# ---- top-down splat ----
def to_uv(P): return np.stack([P@u, P@v],1)
suv = to_uv(sxyz); ruv = to_uv(pts)
allu = np.concatenate([suv, ruv]); umin = allu.min(0)-0.1; umax = allu.max(0)+0.1
PPM = 300
Wpx = int((umax[0]-umin[0])*PPM); Hpx = int((umax[1]-umin[1])*PPM)
def render(layers, R=2):
    canvas = np.full((Hpx, Wpx, 3), 18, np.uint8)
    yy, xx = np.mgrid[-R:R+1,-R:R+1]; disk=(xx*xx+yy*yy)<=R*R
    for uvv, col in layers:
        px = ((uvv-umin)*PPM).astype(int); px[:,1] = Hpx-1-px[:,1]
        for (cx,cy), c in zip(px, col):
            x0,x1 = max(0,cx-R), min(Wpx,cx+R+1); y0,y1 = max(0,cy-R), min(Hpx,cy+R+1)
            if x0>=x1 or y0>=y1: continue
            dm = disk[(y0-cy+R):(y1-cy+R),(x0-cx+R):(x1-cx+R)]
            canvas[y0:y1,x0:x1][dm] = c
    return canvas
Aimg = render([(suv, srgb)])                       # SIFT only
Bimg = render([(suv, srgb),(ruv, rgb)])            # SIFT + maxed rescue
# labels bar
def bar(txt, W):
    from PIL import ImageDraw
    im = Image.new("RGB",(W,34),(30,30,30)); d=ImageDraw.Draw(im); d.text((10,10),txt,fill=(235,235,235)); return np.asarray(im)
labA = bar(f"SIFT production floor  |  {len(sxyz)} pts  {1101} cells  2.75 m2", Wpx)
labB = bar(f"SIFT + MAXED rescue (planesweep+LoFTR)  |  +{len(pts)} rescue pts  2337 cells  5.84 m2", Wpx)
gap = np.full((Hpx+34, 20, 3), 40, np.uint8)
left = np.vstack([labA, Aimg]); right = np.vstack([labB, Bimg])
combo = np.concatenate([left, gap, right], 1)
Image.fromarray(combo).save(FR + "/overlay_floor_maxed.png")
print(f"[render] {Wpx}x{Hpx}/panel PPM={PPM} -> overlay_floor_maxed.png")
# also save the colored merged cloud
fc.write_ply(FR + "/floor_maxed_colored.ply", pts, rgb=rgb)
json.dump({"merged_colored_pts": int(len(pts)), "sift_pts": int(len(sxyz)),
           "panel_px":[Wpx,Hpx], "ppm":PPM}, open(FR+"/fr_render_maxed_stats.json","w"), indent=1)
print("DONE")
