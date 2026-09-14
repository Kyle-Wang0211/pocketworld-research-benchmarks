import os, sys
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth
out = "/root/off_ens/pc.ply"
filter_depth("/root/mvs_P16k", "/root/off_ens", out,
             geo_mask_thres=3, geo_pixel_thres=1.0, geo_depth_thres=0.01,
             photo_thres=[0.3, 0.5, 0.5], method="casdiffmvs", dataset="general")
n=0
with open(out,"rb") as f:
    for _ in range(30):
        l=f.readline()
        if l.startswith(b"element vertex"): n=int(l.split()[-1])
        if l.strip()==b"end_header": break
print(f"ENSEMBLE {n:,} 点  (单次采样官方 = 36,845,259)")
