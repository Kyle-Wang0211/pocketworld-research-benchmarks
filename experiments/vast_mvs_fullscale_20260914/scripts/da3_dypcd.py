#!/usr/bin/env python3
"""DA3-BASE @742 深度 → MonoMVSNet 官方 dypcd 动态几何门(test_dtu_dypcd.py,一行不改)。

几何常数 = DTU 那一套(官方**唯一不挑场景**的全局值):s=1, e=11, dist_base=1/2, rel_diff_base=1/1000。
   TNT 两份(adv/inter)是"一场一套",我们的房间不在表里,用它就得由我挑行 ⇒ 不用。
光度那一半 = DA3 自己的官方门 conf_thresh_percentile=40:把 conf 二值化成 1.0/0.0,
   官方 args.conf 默认 0.55 ⇒ photo_mask 恰好等于"DA3 官方门通过者"。
🔴 副作用记账:官方那句 depth_est_averaged[confidence>0.75]=ref 对所有通过点都成立
   ⇒ 深度平均被关掉,出的是 ref 自己的深度。这与对照臂 ③ 口径一致(③ 直接调
   check_geometric_consistency 也没平均)⇒ ③ 与本臂**唯一变量仍是几何门**。
本文件只做数据搬运,不含任何判据。
"""
import os, sys, shutil, math
import numpy as np
from PIL import Image

NPZ  = os.environ.get("NPZDIR", "/root/da3_r742b")
ROOT = os.environ.get("WORKDIR", "/root/da3_dypcd")
SCAN = "scene0"                       # filter_depth 拿 scan_folder 的 basename 当 key(DTU 版其实不查表)
PAIRSRC = "/root/mono_data/scene0/pair.txt"
OUTPLY = os.environ.get("OUTPLY", "/root/da3_dypcd_742.ply")

sys.path.insert(0, "/root/MonoMVSNet")
os.chdir("/root/MonoMVSNet")
from datasets.data_io import save_pfm

d = np.load(sorted(__import__("glob").glob(f"{NPZ}/exports/npz/*.npz"))[0], allow_pickle=True)
D, C, E, K, I = d["depth"], d["conf"], d["extrinsics"], d["intrinsics"], d["image"]
N, H, W = D.shape
print(f"[IN] {N} 视图 {H}x{W}", flush=True)

thr = float(np.percentile(C, 40.0))                       # DA3 官方默认门
print(f"[IN] DA3 官方 conf p40 = {thr:.4f}", flush=True)

scn = f"{ROOT}/{SCAN}"; out = f"{ROOT}/out"
for p in (f"{scn}/cams", f"{scn}/images", f"{out}/depth_est", f"{out}/confidence"):
    os.makedirs(p, exist_ok=True)
shutil.copy(PAIRSRC, f"{scn}/pair.txt")

img_u8 = I if I.dtype == np.uint8 else (np.clip(I, 0, 1) * 255).astype(np.uint8)
photo_rate = []
for i in range(N):
    Ei = np.eye(4, dtype=np.float32); Ei[:3, :4] = E[i]
    with open(f"{scn}/cams/{i:08d}_cam.txt", "w") as f:
        f.write("extrinsic\n")
        for r in Ei: f.write(" ".join(f"{v:.9f}" for v in r) + "\n")
        f.write("\nintrinsic\n")
        for r in K[i]: f.write(" ".join(f"{v:.9f}" for v in r) + "\n")
        f.write("\n%f %f\n" % (float(D[i][D[i] > 0].min()), float(D[i].max())))
    Image.fromarray(img_u8[i]).save(f"{scn}/images/{i:08d}.jpg", quality=95)
    save_pfm(f"{out}/depth_est/{i:08d}.pfm", D[i].astype(np.float32))
    cb = (C[i] >= thr).astype(np.float32)                  # 二值:1.0 通过 / 0.0 不通过
    photo_rate.append(float(cb.mean()))
    save_pfm(f"{out}/confidence/{i:08d}.pfm", cb)
print(f"[PREP] 写完 {N} 组;photo 通过率 均值 {np.mean(photo_rate):.4f}", flush=True)

# 🔴 预期值对照 1:conf>=p40 ⇒ 通过率理论 = 60%
_exp = 0.60
assert abs(np.mean(photo_rate) - _exp) < 0.01, f"photo 通过率 {np.mean(photo_rate):.4f} 偏离预期 {_exp}"
print(f"[CHECK-1] photo 通过率 实测 {np.mean(photo_rate):.4f} 预期 {_exp:.4f} OK", flush=True)

# 🔴 预期值对照 2:最终点数上界 = 通过 photo 的像素总数
UB = int(round(np.mean(photo_rate) * N * H * W))
print(f"[CHECK-2] 最终点数上界(photo 通过像素数) = {UB:,}", flush=True)

sys.argv = ["x", "--testpath", ROOT, "--testlist", "/dev/null",
            "--outdir", out, "--loadckpt", "/dev/null"]
import importlib.util
spec = importlib.util.spec_from_file_location("dyp", "/root/MonoMVSNet/test_dtu_dypcd.py")
dyp = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(dyp)
except SystemExit: pass
except Exception as ex: print("模块加载警告:", str(ex)[:140], flush=True)

print(f"[CONST] s={dyp.s} e={dyp.e} dist_base={dyp.dist_base} rel_diff_base={dyp.rel_diff_base} "
      f"args.conf={dyp.args.conf}", flush=True)
assert (dyp.s, dyp.e, dyp.dist_base, dyp.rel_diff_base) == (1, 11, 1/2, 1/1000), "DTU 常数被改过"
assert dyp.args.conf == 0.55, "args.conf 不是官方默认 0.55"

# 本场景深度中位 → 把相对容差换算成毫米,打出来备查
_med = float(np.median(D[D > 0]))
for i in (dyp.s, 5, dyp.e - 1):
    _rel = math.log(max(i, 1.05), 10) * dyp.rel_diff_base
    print(f"[LADDER] i={i:2d}  dist<{i*dyp.dist_base:.2f}px  rel<{_rel*100:.4f}%  "
          f"@{_med:.2f}m = {_rel*_med*1000:.3f} mm  需 {i} 票", flush=True)

dyp.filter_depth(scn, scn, out, OUTPLY)
print("[DONE]", OUTPLY, os.path.getsize(OUTPLY), "bytes", flush=True)
