#!/usr/bin/env python3.11
"""E2-B v2 finalize: gray-point NN-color fallback (declared), same-gauge true-color
renders, diff render, operating-point curve, SHA256SUMS. Writes only in this dir."""
import numpy as np, json, os, hashlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = ["Hiragino Sans GB", "PingFang SC", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
from scipy.spatial import cKDTree

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_rs2px_gate"
CAP_DIR = f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17"

def read_ply(path):
    with open(path,"rb") as f:
        h=b""
        while not h.endswith(b"end_header\n"): h += f.readline()
        n=int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d=np.fromfile(f,dtype=rec,count=n)
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)

def write_ply(path, xyz, rgb, comment):
    n=len(xyz)
    with open(path,"wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"comment {comment}\n".encode())
        f.write(f"element vertex {n}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        rec=np.empty(n,dtype=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")]))
        rec["x"],rec["y"],rec["z"]=xyz[:,0].astype("<f4"),xyz[:,1].astype("<f4"),xyz[:,2].astype("<f4")
        rec["r"],rec["g"],rec["b"]=rgb[:,0],rgb[:,1],rgb[:,2]
        rec.tofile(f)

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""): h.update(chunk)
    return h.hexdigest()

prod_xyz, prod_rgb = read_ply(f"{CAP_DIR}/sfm_sparse.ply")
ptree = cKDTree(prod_xyz)

# ---- gray fallback recolor (visual aid, declared in comment) ----
fallback_stats = {}
for name in ["rs2px","mid3px","ours4px"]:
    p = f"{OUT}/{name}_cap50.ply"
    xyz, rgb = read_ply(p)
    gray = (rgb[:,0]==128)&(rgb[:,1]==128)&(rgb[:,2]==128)
    if gray.sum():
        dd, ii = ptree.query(xyz[gray], k=1, workers=-1)
        ok = dd <= 0.05
        gi = np.flatnonzero(gray)
        rgb[gi[ok]] = prod_rgb[ii[ok]]
        fallback_stats[name] = {"gray": int(gray.sum()), "recolored_nn5cm": int(ok.sum())}
    write_ply(p, xyz, rgb,
        f"E2-B v2 cap50 {name}: RS-semantics reproj gate on rebuilt tracks, refined production poses, same gauge; colors=certified recipe (surviving obs full-res bilinear mean) with production-NN<=5cm fallback for {int(gray.sum())} obs-in-missing-photo pts")
print("fallback:", fallback_stats)

z = np.load(f"{OUT}/render_arrays_v2.npz")
base_pts, delta = z["base_pts"], z["delta_in_base"]
hull_xy, cams = z["hull_xy"], z["cams"]
rs_xyz, rs_rgb = read_ply(f"{OUT}/rs2px_cap50.ply")
b4_xyz, b4_rgb = read_ply(f"{OUT}/ours4px_cap50.ply")

# shared view limits from production cloud (robust)
lim = {}
for k, idx in (("x",0),("y",1),("z",2)):
    lo, hi = np.percentile(prod_xyz[:,idx],[0.2,99.8])
    pad = 0.35*(hi-lo)*0.15 + 0.25
    lim[k] = (lo-pad, hi+pad)

def panel(ax, pts, rgb, view, title, npts=None):
    i, j = (0,2) if view=="top" else (0,1)
    ax.scatter(pts[:,i], pts[:,j], s=0.25, c=np.clip(rgb/255.0,0,1), marker=".", linewidths=0, rasterized=True)
    ax.set_xlim(lim["x"]); ax.set_ylim(lim["z"] if view=="top" else lim["y"])
    if view!="top": ax.invert_yaxis()
    ax.set_aspect("equal"); ax.set_facecolor("#0d0d11")
    ax.set_title(f"{title}\n{len(pts):,} pts", color="#ddd", fontsize=9)
    ax.tick_params(colors="#666", labelsize=6)
    for s in ax.spines.values(): s.set_color("#333")

for view in ["top","elev"]:
    fig, axes = plt.subplots(1,3, figsize=(16,6), facecolor="#0d0d11")
    panel(axes[0], prod_xyz, prod_rgb, view, "production sfm_sparse.ply (context)")
    panel(axes[1], b4_xyz, b4_rgb, view, "rebuilt tracks @4px (ours, control)")
    panel(axes[2], rs_xyz, rs_rgb, view, "rebuilt tracks @2.0px (RS default)")
    if view=="top":
        for ax in axes:
            hp = np.vstack([hull_xy, hull_xy[:1]])
            ax.plot(hp[:,0], hp[:,1], "-", color="#2e8fff", lw=0.8, alpha=0.8)
            ax.scatter(cams[:,0], cams[:,2], s=2, c="#2e8fff", marker="x", linewidths=0.5)
    fig.suptitle(f"E2-B cap50 同gauge真彩对比({'俯视 X-Z + 相机hull蓝线' if view=='top' else '立面 X-Y'})— 生产坐标系直出,无对齐", color="#eee", fontsize=11)
    fig.tight_layout()
    fig.savefig(f"{OUT}/compare_truecolor_{view}.png", dpi=170, facecolor="#0d0d11")
    plt.close(fig)

# diff render: baseline gray, killed-by-2px red
fig, axes = plt.subplots(1,2, figsize=(13,6), facecolor="#0d0d11")
for ax, view in zip(axes, ["top","elev"]):
    i, j = (0,2) if view=="top" else (0,1)
    ax.scatter(base_pts[~delta][:,i], base_pts[~delta][:,j], s=0.25, c="#555", marker=".", linewidths=0, rasterized=True)
    ax.scatter(base_pts[delta][:,i], base_pts[delta][:,j], s=0.4, c="#ff3030", marker=".", linewidths=0, rasterized=True)
    if view=="top":
        hp = np.vstack([hull_xy, hull_xy[:1]])
        ax.plot(hp[:,0], hp[:,1], "-", color="#2e8fff", lw=0.8)
    ax.set_xlim(lim["x"]); ax.set_ylim(lim["z"] if view=="top" else lim["y"])
    if view!="top": ax.invert_yaxis()
    ax.set_aspect("equal"); ax.set_facecolor("#0d0d11")
    ax.set_title("俯视" if view=="top" else "立面", color="#ddd", fontsize=10)
    ax.tick_params(colors="#666", labelsize=6)
    for s in ax.spines.values(): s.set_color("#333")
fig.suptitle(f"被 RS 2.0px 门裁掉的点(红,{int(delta.sum()):,})叠在 4px 基线(灰,{len(base_pts):,})上 — 红点遍布真面,非集中拖尾区", color="#eee", fontsize=11)
fig.tight_layout()
fig.savefig(f"{OUT}/diff_killedby2px.png", dpi=170, facecolor="#0d0d11")
plt.close(fig)

# operating curve
s = json.load(open(f"{OUT}/stats_v2.json"))
gates = [1.5,2.0,2.5,3.0,3.5,4.0]
tk = [s["gate_sweep"][str(g)]["trail_kill_rate_pct"] for g in gates]
fk = [s["gate_sweep"][str(g)]["dense_false_kill_pct"] for g in gates]
cov0 = s["gate_sweep"]["4.0"]["ruler_2_floor"]["cover_cells_2cm"]
cov = [100*(1 - s["gate_sweep"][str(g)]["ruler_2_floor"]["cover_cells_2cm"]/cov0) for g in gates]
oh = [s["gate_sweep"][str(g)]["outside_hull_kill_pct"] for g in gates]
fig, ax = plt.subplots(figsize=(8,5.5), facecolor="white")
ax.plot(gates, tk, "o-", color="#d62728", label="拖尾杀灭率 SIG_ISO kill %")
ax.plot(gates, oh, "s--", color="#ff7f0e", label="hull外点杀灭率 %")
ax.plot(gates, fk, "o-", color="#1f77b4", label="密集真面误杀率 DENSE %")
ax.plot(gates, cov, "^-", color="#2ca02c", label="地板正确覆盖损失 %")
ax.axvline(2.0, color="#888", ls=":", lw=1); ax.text(2.02, max(tk)*0.95, "RS默认2.0px", fontsize=8, color="#555")
ax.axvline(4.0, color="#bbb", ls=":", lw=1); ax.text(3.72, max(tk)*0.95, "我们4px", fontsize=8, color="#777")
ax.set_xlabel("reprojection gate (px)"); ax.set_ylabel("%")
ax.set_title("E2-B cap50 操作点曲线:收紧 reproj 门的拖尾杀灭 vs 真点/覆盖代价\n(基线=rebuilt@4px;选择性仅 ~1.7-2×,不是免费刀)", fontsize=10)
ax.legend(fontsize=9); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/operating_curve.png", dpi=160)
plt.close(fig)

# SHA256SUMS
files = sorted(f for f in os.listdir(OUT) if f.endswith((".ply",".png",".json")) and not f.startswith("_"))
with open(f"{OUT}/SHA256SUMS.txt","w") as f:
    for fn in files:
        f.write(f"{sha256(os.path.join(OUT,fn))}  {fn}\n")
json.dump(fallback_stats, open(f"{OUT}/color_fallback.json","w"), indent=2)
print("renders + SHAs done")
