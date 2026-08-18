# DA3 分离度探针 - 步骤1: 数据准备(修订版)
# 定案: out_P16k 深度图/mask/dense_P16k.ply 与 mvs_P16k/cams 的 cam.txt 同一世界(gauge),
#       相似变换拟合=恒等(scale 0.9997, res med 0.005 gauge)。COLMAP work模型是另一套位姿解, 不用。
# 锚点 = lightglue_spike/ply_P16KH.ply(同 gauge 世界的稀疏云, 法医"sparse"同源)投影。
import numpy as np, json
from PIL import Image

SC = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad"
WALL = SC + "/wall"
OUT = SC + "/da3probe"
BASE = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
SPARSE_PLY = "/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply"
FRAMES = [78, 79, 80, 81, 82, 83, 85, 86, 87, 100, 103, 107, 125]
S768 = 768 / 4032.0

# ---- 墙面口径(法医产物,原样复用) ----
nfl = np.load(WALL + "/floor.npy"); up = nfl[:3]; dfl = nfl[3]
nw = np.array([0.46, -0.679, -0.572]); nw /= np.linalg.norm(nw)
u_ = np.cross(up, nw); u_ /= np.linalg.norm(u_); v_ = np.cross(nw, u_)
DW = 4.734  # 粗平面(选区口径, quant_final.py 原样)
mw = json.load(open("/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/wall_forensics_20260818/measure_wall.json"))
NV = np.array(mw["P16k"]["nv"]); DFIT = mw["P16k"]["d"]  # 真值平面(稳健拟合)

def read_cam(fr):
    L = open(f"{BASE}/mvs_P16k/cams/{fr:08d}_cam.txt").read().split("\n")
    E = np.array([[float(x) for x in L[i + 1].split()] for i in range(4)])
    K = np.array([[float(x) for x in L[i + 7].split()] for i in range(3)])
    dmm = [float(x) for x in L[11].split()]
    return E, K, dmm

def read_pfm(fp):
    with open(fp, "rb") as f:
        assert f.readline().strip() == b"Pf"
        w, h = map(int, f.readline().split()); scale = float(f.readline())
        d = np.frombuffer(f.read(w * h * 4), dtype="<f4" if scale < 0 else ">f4").reshape(h, w)
        return np.flipud(d).copy()

def read_ply(fp):
    with open(fp, "rb") as f:
        hdr = b""
        while True:
            l = f.readline(); hdr += l
            if l.strip() == b"end_header": break
        n = int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        DT = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
        M = np.frombuffer(f.read(n * DT.itemsize), dtype=DT)
    return np.stack([M["x"], M["y"], M["z"]], 1).astype(np.float64)

SPTS = read_ply(SPARSE_PLY)
print("sparse anchors total:", len(SPTS))

offs = np.load(WALL + "/offs.npy"); blobI = np.load(WALL + "/blob_idx.npy")
summary = {}
for fr in FRAMES:
    E, Kfull, dmm = read_cam(fr)
    R = E[:3, :3]; t = E[:3, 3]
    D = read_pfm(f"{BASE}/out_P16k/depth_est/{fr:08d}.pfm")
    mk = np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png")) > 0
    H, W = D.shape
    Ks = Kfull.copy(); Ks[:2] *= S768
    yy, xx = np.nonzero(mk)
    dpx = D[yy, xx].astype(np.float64)
    ptc = np.stack([(xx - Ks[0, 2]) / Ks[0, 0], (yy - Ks[1, 2]) / Ks[1, 1], np.ones(len(xx))], 1)
    XW = (ptc * dpx[:, None] - t) @ R  # gauge 世界
    r = XW @ nw + DW; pu = XW @ u_; pv = XW @ v_
    inb = (pu > -4.2) & (pu < 0.2) & (pv > -1.7) & (pv < 1.7)
    clean = inb & (np.abs(r) < 0.06)
    blob_recalc = inb & (r > -0.55) & (r < -0.08)
    # 溯源 blob 像素(权威)
    m = (blobI >= offs[fr]) & (blobI < offs[fr + 1])
    loc = blobI[m] - offs[fr]
    agree = float(blob_recalc[loc].mean()) if len(loc) else float("nan")
    # 真值平面 z-depth(整幅 mask 像素)
    C = -R.T @ t
    dirs = ptc @ R
    denom = dirs @ NV
    dplane = -(C @ NV + DFIT) / denom
    # 入射角(平面法向与视线夹角余弦, 记录用)
    cosw = np.abs(denom) / np.linalg.norm(dirs, axis=1)
    # ---- 锚点: 稀疏云投影 ----
    XC = SPTS @ R.T + t
    z = XC[:, 2]
    ok = z > 0.5
    px = XC[ok, 0] / z[ok] * Kfull[0, 0] + Kfull[0, 2]
    py = XC[ok, 1] / z[ok] * Kfull[1, 1] + Kfull[1, 2]
    zin = z[ok]
    inim = (px >= 0) & (px < 4032) & (py >= 0) & (py < 3024)
    px, py, zin = px[inim], py[inim], zin[inim]
    # 宽松遮挡门: 与 MVS 深度差 <15% 才收(记录门前门后数量)
    ix = np.clip((px * S768).astype(int), 0, W - 1)
    iy = np.clip((py * S768).astype(int), 0, H - 1)
    dm = D[iy, ix]
    vis = (dm > 0) & (np.abs(zin - dm) / np.maximum(dm, 1e-6) < 0.15)
    summary[fr] = dict(
        n_mask=int(mk.sum()), n_clean=int(clean.sum()),
        n_blob_prov=int(len(loc)), n_blob_recalc=int(blob_recalc.sum()), blob_agree=agree,
        r_blob_med=float(np.median(r[loc])) if len(loc) else None,
        r_clean_rms=float(np.sqrt(np.mean(r[clean] ** 2))) if clean.sum() else None,
        n_anchor_raw=int(inim.sum()), n_anchor_vis=int(vis.sum()),
        cosw_med_blob=float(np.median(cosw[loc])) if len(loc) else None,
        depth_minmax=dmm)
    np.savez_compressed(
        f"{OUT}/frame_{fr}.npz",
        yy=yy.astype(np.int32), xx=xx.astype(np.int32),
        depth_mvs=dpx.astype(np.float32), depth_plane=dplane.astype(np.float32),
        r=r.astype(np.float32), cosw=cosw.astype(np.float32),
        clean=clean, blob_recalc=blob_recalc, blob_loc=loc.astype(np.int64),
        anchor_px=px.astype(np.float32), anchor_py=py.astype(np.float32),
        anchor_z=zin.astype(np.float32), anchor_vis=vis,
        E=E, Kfull=Kfull)
    print(fr, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in summary[fr].items() if k != "depth_minmax"}, ensure_ascii=False))

json.dump(summary, open(OUT + "/prep_summary.json", "w"), indent=1)
print("OK")
