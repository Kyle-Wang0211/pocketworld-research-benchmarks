#!/usr/bin/env python3
"""Export the per-view depth maps that survive each engine s OFFICIAL gate, plus colour and camera.
These are the exact pixels that produced the point clouds on the comparison page -- TSDF is fed the
same filtered depths, nothing else changes."""
import sys, os, glob, numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import read_pfm, read_camera_parameters, read_img, read_pair_file, check_geometric_consistency

ENGINE, OUT = sys.argv[1], sys.argv[2]
for s in ("depth", "color", "cam"): os.makedirs(f"{OUT}/{s}", exist_ok=True)

if ENGINE == "casdiff":
    SRC = "/root/out_official"; PAIR = "/root/mvs_P16k/pair.txt"
    pair = read_pair_file(PAIR, "general")
    for ref, srcs in pair:
        Kr, Er, dmax, dmin = read_camera_parameters(f"{SRC}/cams/{ref:08d}_cam.txt")
        img = read_img(f"{SRC}/images/{ref:08d}.jpg")
        dref = read_pfm(f"{SRC}/depth_est/{ref:08d}.pfm")[0]
        c0 = read_pfm(f"{SRC}/conf0/{ref:08d}.pfm")[0]; c1 = read_pfm(f"{SRC}/conf1/{ref:08d}.pfm")[0]; c2 = read_pfm(f"{SRC}/conf2/{ref:08d}.pfm")[0]
        photo = (c0 > 0.3) & (c1 > 0.5) & (c2 > 0.5)                       # official photo_thres
        gsum = 0; rsum = 0
        for s in srcs:
            Ks, Es, _, _ = read_camera_parameters(f"{SRC}/cams/{s:08d}_cam.txt")
            ds = read_pfm(f"{SRC}/depth_est/{s:08d}.pfm")[0]
            gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, ds, Ks, Es, dmax, dmin, 1.0, 0.01)
            gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
        davg = (rsum + dref) / (gsum + 1)
        final = photo & (gsum >= 3)
        np.save(f"{OUT}/depth/{ref:08d}.npy", np.where(final, davg, 0).astype(np.float32))
        cv2.imwrite(f"{OUT}/color/{ref:08d}.png", (img[:, :, ::-1] * 255).astype(np.uint8))
        np.savez(f"{OUT}/cam/{ref:08d}.npz", K=Kr.astype(np.float64), E=Er.astype(np.float64))
        if ref % 40 == 0: print(f"  ref {ref} keep {final.mean():.3f}", flush=True)

elif ENGINE == "pda":
    DD = "/root/regionmerge/pda_out/depth_npy"; CAM = "/root/regionmerge/sfm768"; RGB = "/root/regionmerge/rgb768"
    PAIR = "/root/mvs_P16k/pair.txt"
    pair = read_pair_file(PAIR, "general")
    D = {int(os.path.basename(f)[:8]): np.load(f).astype(np.float32) for f in glob.glob(f"{DD}/*.npy")}
    def cam(i):
        return (np.loadtxt(f"{CAM}/intrinsic/{i:08d}.txt").astype(np.float32),
                np.loadtxt(f"{CAM}/pose/{i:08d}.txt").astype(np.float32))
    for ref, srcs in pair:
        Kr, Er = cam(ref); dref = D[ref]; gsum = 0; rsum = 0
        for s in srcs:
            Ks, Es = cam(s)
            gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, D[s], Ks, Es, 30.0, 0.5, 1.0, 0.01)
            gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
        davg = (rsum + dref) / (gsum + 1)
        final = (gsum >= 3) & (dref > 0)
        np.save(f"{OUT}/depth/{ref:08d}.npy", np.where(final, davg, 0).astype(np.float32))
        img = cv2.imread(f"{RGB}/{ref:08d}.jpg")
        cv2.imwrite(f"{OUT}/color/{ref:08d}.png", img)
        np.savez(f"{OUT}/cam/{ref:08d}.npz", K=Kr.astype(np.float64), E=Er.astype(np.float64))
        if ref % 40 == 0: print(f"  ref {ref} keep {final.mean():.3f}", flush=True)
else:
    raise SystemExit("unknown engine")
print("DONE", ENGINE, len(glob.glob(f"{OUT}/depth/*.npy")), flush=True)
