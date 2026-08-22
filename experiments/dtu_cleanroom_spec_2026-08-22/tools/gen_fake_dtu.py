#!/usr/bin/env python3
"""格式 smoke:生成 2 个假场景(解析几何,无渲染器),验证 dtu.py 契约理解正确。

假场景 = 一面正对的平板(深度可解析),49 机位布在球面扇区,内参按 1/4 分辨率写。
判据:① MVSDataset 全量遍历不抛错 ② 用 proj_matrices 把 GT 深度重投影,误差 <0.5px
"""
import os, sys, json
import numpy as np, cv2

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fake_dtu"
rng = np.random.default_rng(20260822)

W_HR, H_HR = 1600, 1200            # Depths_raw 分辨率
W_LR, H_LR = 640, 512              # Rectified 分辨率
# 🔴 640×512 不是 1600×1200 的等比缩放!loader 是 半采(→800×600)+ 中心裁(→640×512)。
#    裁剪平移主点 ⇒ 正确链条:物理相机 K_HR(1600×1200)→ K_crop = K_HR*0.5, cx-=80, cy-=44
#    → 写盘 K_FILE = K_crop/4。第一版把两套内参写矛盾,真测试(解析平面)偏 81mm 才抓到。
K_HR = np.array([[1750.0, 0, 800.0], [0, 1750.0, 600.0], [0, 0, 1]])
K_crop = K_HR.copy(); K_crop[:2] *= 0.5
K_crop[0, 2] -= (800 - W_LR) / 2          # cx -= 80
K_crop[1, 2] -= (600 - H_LR) / 2          # cy -= 44
K_FILE = K_crop.copy(); K_FILE[:2] /= 4.0

def look_at(eye, target):
    z = target - eye; z /= np.linalg.norm(z)
    x = np.cross(np.array([0., -1., 0.]), z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])                       # world→cam 旋转
    t = -R @ eye
    E = np.eye(4); E[:3, :3] = R; E[:3, 3] = t
    return E

# 49 机位:球面扇区,半径 650mm,注视原点(尺度与 depth_max≈935mm 自洽)
poses = []
for i in range(49):
    az = np.deg2rad(-40 + 80 * (i % 7) / 6)
    el = np.deg2rad(15 + 40 * (i // 7) / 6)
    r = 650.0
    eye = np.array([r*np.cos(el)*np.sin(az), -r*np.sin(el), -r*np.cos(el)*np.cos(az)])
    poses.append(look_at(eye, np.zeros(3)))

def save_pfm(fn, img):
    with open(fn, "wb") as f:
        f.write(b"Pf\n"); f.write(f"{img.shape[1]} {img.shape[0]}\n".encode())
        f.write(b"-1.0\n"); np.flipud(img).astype("<f4").tofile(f)

def plane_depth(E, K, W, H):
    """场景 = 世界系平面 z=+300mm(法向 -z,面向相机群)。逐像素解析求深度。"""
    R, t = E[:3, :3], E[:3, 3]
    uu, vv = np.meshgrid(np.arange(W)+0.5, np.arange(H)+0.5)
    rays = np.stack([(uu-K[0,2])/K[0,0], (vv-K[1,2])/K[1,1], np.ones_like(uu)], -1)
    Rw = R.T; ow = -R.T @ t                      # cam→world
    d_w = rays @ Rw.T
    # 平面 z_w = 300:  ow_z + s*d_z = 300  ⇒ s = (300-ow_z)/d_z
    s = (300.0 - ow[2]) / d_w[..., 2]
    depth = s.astype(np.float32)                  # s 即沿光轴深度(rays z=1 归一化)
    depth[s <= 0] = 0
    return depth

os.makedirs(f"{OUT}/Cameras/train", exist_ok=True)
# pair.txt:全局一份。分数用共视度的简化替身(机位相邻度),格式正确即可
with open(f"{OUT}/Cameras/pair.txt", "w") as f:
    f.write("49\n")
    for i in range(49):
        near = sorted(range(49), key=lambda j: abs(j-i))[1:11]
        f.write(f"{i}\n10 " + " ".join(f"{j} {1000-abs(j-i)}" for j in near) + " \n")
for vid, E in enumerate(poses):
    with open(f"{OUT}/Cameras/train/{vid:08d}_cam.txt", "w") as f:
        f.write("extrinsic\n")
        for r in E: f.write(" ".join(f"{x:.6f}" for x in r) + "\n")
        f.write("\nintrinsic\n")
        for r in K_FILE: f.write(" ".join(f"{x:.6f}" for x in r) + "\n")
        f.write("\n425.0 2.5\n")                  # depth_min depth_interval(DTU 惯例量级)

for scan in ("scan1", "scan2"):
    os.makedirs(f"{OUT}/Rectified/{scan}_train", exist_ok=True)
    os.makedirs(f"{OUT}/Depths_raw/{scan}", exist_ok=True)
    for vid, E in enumerate(poses):
        d_hr = plane_depth(E, K_HR, W_HR, H_HR)
        save_pfm(f"{OUT}/Depths_raw/{scan}/depth_map_{vid:04d}.pfm", d_hr)
        mask = ((d_hr > 0) * 255).astype(np.uint8)
        cv2.imwrite(f"{OUT}/Depths_raw/{scan}/depth_visual_{vid:04d}.png", mask)
        for light in range(7):
            img = np.full((H_LR, W_LR, 3), 40 + 25*light, np.uint8)
            cv2.putText(img, f"{scan} v{vid} L{light}", (30, 260),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
            cv2.imwrite(f"{OUT}/Rectified/{scan}_train/rect_{vid+1:03d}_{light}_r5000.png", img)
print(f"  假数据已生成 → {OUT}")

# ── 契约验证 ──
# ⚠️ 判据必须是"世界点落在解析平面上":它同时检验内参坐标系/外参/深度裁剪对齐。
#    同一套 K/E 来回投影(下面的闭环)数学上恒等,只能抓 NaN/形状错,当不了判据。
sys.path.insert(0, os.environ.get("DIFFMVS_REPO",
    os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")))
with open(f"{OUT}/list.txt", "w") as f: f.write("scan1\nscan2\n")
from datasets.dtu import MVSDataset
ds = MVSDataset(OUT, f"{OUT}/list.txt", "train", 5, 384)
print(f"  metas = {len(ds)}(应为 2 场景×49 机位×7 光照 = 686)")
errs = []
for idx in rng.choice(len(ds), 24, replace=False):
    s = ds[int(idx)]
    d4 = s["depth"]["stage4"]; m4 = s["mask"]["stage4"]
    pm = s["proj_matrices"]["stage4"]           # [nviews,2,4,4],ref 在 0
    E0, K0 = pm[0, 0], pm[0, 1, :3, :3]
    v, u = np.nonzero(m4 > 0.5)
    pick = rng.choice(len(v), 200, replace=False)
    u_, v_, z = u[pick]+0.5, v[pick]+0.5, d4[v[pick], u[pick]]
    # 反投影到世界再投回来,闭环应 <0.5px(检验内参/外参/深度三者自洽)
    xyz_c = np.stack([(u_-K0[0,2])/K0[0,0]*z, (v_-K0[1,2])/K0[1,1]*z, z], -1)
    R0, t0 = E0[:3, :3], E0[:3, 3]
    xyz_w = (xyz_c - t0) @ R0
    back = (xyz_w @ R0.T + t0) @ K0.T
    uv = back[:, :2] / back[:, 2:3]
    errs.append(np.abs(uv - np.stack([u_, v_], -1)).max())
print(f"  重投影闭环最大误差 {max(errs):.4f}px  {'✅ <0.5px 通过' if max(errs)<0.5 else '🔴 FAIL'}")
# 真判据:反投影世界点 → 解析平面 z_w=300
worst = 0
for idx in rng.choice(len(ds), 20, replace=False):
    s2 = ds[int(idx)]
    d4 = s2["depth"]["stage4"]; m4 = s2["mask"]["stage4"] > 0.5
    pm2 = s2["proj_matrices"]["stage4"]
    E0, K0 = pm2[0, 0], pm2[0, 1, :3, :3]
    vv2, uu2 = np.nonzero(m4)
    pk = rng.choice(len(vv2), 300, replace=False)
    u2, v2, z2 = uu2[pk]+0.5, vv2[pk]+0.5, d4[vv2[pk], uu2[pk]]
    xc = np.stack([(u2-K0[0,2])/K0[0,0]*z2, (v2-K0[1,2])/K0[1,1]*z2, z2], -1)
    R0, t0 = E0[:3, :3], E0[:3, 3]
    xw = (xc - t0) @ R0
    worst = max(worst, float(np.abs(xw[:, 2] - 300.0).max()))
print(f"  真判据:世界点到解析平面最大偏差 {worst:.3f} mm")
print("  SMOKE_OK" if worst < 2.0 and len(ds) == 686 else "  SMOKE_FAIL")
