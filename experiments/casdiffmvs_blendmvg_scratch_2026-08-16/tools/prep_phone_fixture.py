#!/usr/bin/env python3
"""从真机 capture 建 MVS fixture(97 帧)——现役管线产物,取代 2026-06 的老 414 帧。

数据来源(全部来自设备,非 host 复算):
  照片   photos_highres/*.jpg.lep  → Lepton 逐字节还原成原始 JPEG 4032×3024
  内参   photos_highres_sidecars.zpaq 的 intrinsics_fxfycxcy
  位姿   official_sfm_sparse_meta.json 的 refined poses(97 条)
  真值   official_sfm_sparse.ply(49253 点)
  帧号桥 official_sfm_fed_frames.jsonl 的 frameId ↔ jpegPath

🔴 位姿轴系(投影实测判定,不是照注释写):
   fed_frames 的注释说喂进去的是 ARKit 相机轴、未施加 COLMAP 翻转,
   但 **refined 输出已是 COLMAP/OpenCV 轴系** ——
   实测:原样 98.6% 点在相机前 / 补 diag(1,-1,-1) 只剩 1.4%。⇒ **不补翻转**。

🔴 帧号不能按下标推:frameId 0→tap-8, 1→tap-19, 2→tap-29,跳号无规律。

生产口径(取自 casdiffmvs-production-gap 备忘,非自拟):
  深度范围 lo=p2*0.70, hi=p99.5*1.5(<8 点回退 [0.3,4.0] m)
  view selection = MVSNet 角度打分 θ0=5°, σ1=1, σ2=10 + **最小基线 6cm**

⚠️ 可见性用"投影落在图内且 z>0"近似(忽略遮挡)——
   真 track 可见性只在重建里,而我们只有点云 PLY,db 也只有 2D keypoints。
✅ 缩放是**等比** 4032×3024 → 768×576(4:3→4:3,K 逐轴缩放且两轴同因子)。
"""
from __future__ import annotations
import json, os, sys
import numpy as np
from PIL import Image

O = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/kaidongwang/Documents/progecttwo/_host_experiments/phone_cap_20260811"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"{O}/fixture97"
W = int(os.environ.get("FIX_W", 768))
H = int(os.environ.get("FIX_H", 576))
NSRC = int(os.environ.get("FIX_NSRC", 4))
assert abs(W/H - 4032/3024) < 1e-3, f"{W}×{H} 不是 4:3 —— 素材是 4032×3024,拉伸会引入训练分布外的形变"
assert W % 32 == 0 and H % 32 == 0, f"{W}×{H} 不是 32 的倍数,四级金字塔会错位"
# 🔴 必须等比:4032×3024 = 4:3,768×576 也是 4:3
# 08-17 修正:原先 896×512 把 4:3 拉进 16:9,竖直压 1.31× —— 训练分布里没有的形变。
# 选 768×576 的三条理由(不是随便挑一个 4:3):
#   ① 精确 4:3,零形变;32 整除,四级金字塔安全
#   ② **正是 BlendedMVS 的原生分辨率** —— CasDiffMVS 就在这个尺寸上训的,贴回训练分布
#   ③ 442,368 px 比 896×512 的 458,752 还少 3.6% ⇒ 端上预算不涨反降
THETA0, SIG1, SIG2, MIN_BASE = 5.0, 1.0, 10.0, 0.06

# ── 08-17 新增:把管线本来就产出、但一直没被用上的 sidecar 参数接进来 ──
# 每个都是开关,便于单臂对照(合并臂 = 全开)。
USE_ARKIT = os.environ.get("USE_ARKIT", "0") == "1"   # 深度范围并入 ARKit 锚点
DR_LO = float(os.environ.get("DR_LO", 0.70))          # 下缘余量(生产口径 0.70)
DR_HI = float(os.environ.get("DR_HI", 1.50))          # 上缘余量(生产口径 1.50)
FRAME_GATE = os.environ.get("FRAME_GATE", "0") == "1" # 坏帧不做源视图
DT_MAX = float(os.environ.get("DT_MAX", 0.10))        # |request_to_capture_dt| 上限(秒)

# 🔴 FRAME_GATE 只把坏帧**排除出源视图候选**,绝不删除它作为参考帧 ——
#    每一帧照样出深度图。这与"永久缺帧绝对禁止"不冲突:没有任何一帧被丢掉,
#    只是不拿追踪异常/曝光延迟大的帧去给别人当匹配依据。

os.makedirs(OUT, exist_ok=True)


def q2R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


meta = json.load(open(f"{O}/official_sfm_sparse_meta.json"))
fed = {json.loads(l)["frameId"]: json.loads(l)
       for l in open(f"{O}/official_sfm_fed_frames.jsonl") if l.strip()}
poses = [p for p in meta["poses"] if p.get("registered")]
poses.sort(key=lambda p: p["frame_id"])          # 稳定顺序
NF = len(poses)
print(f"注册帧 {NF}(meta 共 {len(meta['poses'])} 条)")

# 稀疏点
raw = open(f"{O}/official_sfm_sparse.ply", "rb").read()
he = raw.index(b"end_header\n") + 11
npt = int([l for l in raw[:he].decode("latin1").split("\n")
           if "element vertex" in l][0].split()[-1])
rec = np.frombuffer(raw[he:he+npt*15],
                    dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                           ("r", "u1"), ("g", "u1"), ("b", "u1")])
P = np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)
print(f"稀疏点 {len(P)}")

names, Ks, Rs, ts, Cs, vis = [], [], [], [], [], []
ark_depths, ark_C, bad_frame = [], [], []
for p in poses:
    fid = p["frame_id"]
    jpg = os.path.basename(fed[fid]["jpegPath"])
    sc = json.load(open(f"{O}/sidecars/{jpg.replace('.jpg','.json')}"))

    # ARKit 位姿是 simd_float4x4 的**列主序**序列化 —— 按行主序读会得到全零平移
    # (踩过:轨迹步长全 0,差点据此误判"两者尺度不一致")。
    E = np.array(sc["extrinsic"], float).reshape(4, 4)
    if np.allclose(E.T[3], [0, 0, 0, 1], atol=1e-3):
        E = E.T
    ark_C.append(E[:3, 3])
    aw = sc.get("anchors_world")
    if aw:
        # ARKit 相机 -Z 朝前 ⇒ 深度 = -(锚点在相机系的 z)
        zc = -((np.array(aw, float) - E[:3, 3]) @ E[:3, :3])[:, 2]
        ark_depths.append(zc[zc > 0.05])
    else:
        ark_depths.append(np.array([]))
    bad_frame.append(not sc.get("is_tracking", True)
                     or sc.get("trackingStateName") != "normal"
                     or abs(sc.get("request_to_capture_dt", 0.0)) > DT_MAX)

    fx, fy, cx, cy = sc["intrinsics_fxfycxcy"]
    ow, oh = sc["image_w"], sc["image_h"]
    sx, sy = W/ow, H/oh                       # 非等比,K 逐轴缩放
    K = np.array([[fx*sx, 0, cx*sx], [0, fy*sy, cy*sy], [0, 0, 1]])
    R = q2R(p["quat_wxyz"]); t = np.array(p["t"], float)
    names.append(jpg); Ks.append(K); Rs.append(R); ts.append(t)
    Cs.append(-R.T @ t)
    # 可见性(近似):z>0 且投影落在缩放后的图内
    Xc = (R @ P.T).T + t
    z = Xc[:, 2]
    u = np.where(z > 0, K[0, 0]*Xc[:, 0]/np.where(z > 0, z, 1)+K[0, 2], -1)
    v = np.where(z > 0, K[1, 1]*Xc[:, 1]/np.where(z > 0, z, 1)+K[1, 2], -1)
    vis.append((z > 0) & (u >= 0) & (u < W) & (v >= 0) & (v < H))
Cs = np.array(Cs)
ark_C = np.array(ark_C)
bad_frame = np.array(bad_frame)

# ── COLMAP↔ARKit 尺度:用**相机轨迹步长**求,不用深度 ──
# 🔴 判据必须选对:逐帧深度比的变异系数高达 0.75,但那不是尺度不稳,是两套点
#    采样了场景的不同部分(ARKit 锚点长在追踪特征上,SfM 点长在匹配特征上)。
#    轨迹步长同时刻同物理相机,是干净判据 —— 实测变异系数 0.037。
_d1 = np.linalg.norm(np.diff(Cs, axis=0), axis=1)
_d2 = np.linalg.norm(np.diff(ark_C, axis=0), axis=1)
_g = (_d1 > 1e-3) & (_d2 > 1e-3)
ARK_SCALE = float(np.median(_d1[_g] / _d2[_g])) if _g.sum() >= 10 else 1.0
_cv = float(np.std(_d1[_g] / _d2[_g]) / np.mean(_d1[_g] / _d2[_g])) if _g.sum() >= 10 else 9.9
print(f"COLMAP/ARKit 尺度 {ARK_SCALE:.4f}(变异系数 {_cv:.4f},{_g.sum()} 段)")
if USE_ARKIT and _cv > 0.15:
    sys.exit("🔴 轨迹尺度逐段不稳,ARKit 锚点不可用于深度范围 —— 停,别出个假先验")
print(f"追踪异常/曝光延迟>{DT_MAX}s 的帧 {bad_frame.sum()}/{NF}"
      + ("(FRAME_GATE 开:不做源视图,仍各自出深度图)" if FRAME_GATE else "(未启用门控)"))

# ── 邻居:MVSNet 角度打分 + 最小基线 ──
neigh = np.zeros((NF, NSRC), np.int32)
drange = np.zeros((NF, 2), np.float32)
angs = []
for i in range(NF):
    sc_ = []
    for j in range(NF):
        if i == j:
            continue
        base = np.linalg.norm(Cs[i]-Cs[j])
        if base < MIN_BASE:                    # 生产口径:最小基线 6cm
            continue
        if FRAME_GATE and bad_frame[j]:        # 坏帧不给别人当源视图(自己仍出深度图)
            continue
        com = vis[i] & vis[j]
        if com.sum() < 20:
            continue
        X = P[com]
        v1 = X-Cs[i]; v2 = X-Cs[j]
        v1 /= np.linalg.norm(v1, axis=1, keepdims=True)+1e-12
        v2 /= np.linalg.norm(v2, axis=1, keepdims=True)+1e-12
        th = np.degrees(np.arccos(np.clip((v1*v2).sum(1), -1, 1)))
        s = np.where(th <= THETA0, np.exp(-(th-THETA0)**2/(2*SIG1**2)),
                     np.exp(-(th-THETA0)**2/(2*SIG2**2))).sum()
        sc_.append((s, float(np.median(th)), j))
    sc_.sort(reverse=True)
    picked = [j for _, _, j in sc_[:NSRC]]
    while len(picked) < NSRC:                  # 交付无损:宁可质量低不可缺帧
        d = np.linalg.norm(Cs-Cs[i], axis=1); d[i] = 1e9
        for q in picked:
            d[q] = 1e9
        picked.append(int(np.argmin(d)))
    neigh[i] = picked
    if sc_:
        angs.append(np.median([a for _, a, _ in sc_[:NSRC]]))
    # 深度范围(生产口径)
    zc = ((Rs[i] @ P[vis[i]].T).T + ts[i])[:, 2] if vis[i].sum() else np.array([])
    zc = zc[zc > 0]
    if USE_ARKIT and ark_depths[i].size >= 30:
        # 并集而非二选一:两套点覆盖的表面不同(实测逐帧中位深度差异大而尺度一致),
        # 各自补对方盲区 ⇒ 合起来的范围既不漏近物也不漏远墙。
        zc = np.concatenate([zc, ark_depths[i] * ARK_SCALE])
    if len(zc) >= 8:
        drange[i] = (np.percentile(zc, 2)*DR_LO, np.percentile(zc, 99.5)*DR_HI)
    else:
        drange[i] = (0.3, 4.0)
neigh.tofile(f"{OUT}/neighbors.i32")
print(f"中位三角化角 {np.median(angs):.2f}°  (p10 {np.percentile(angs,10):.2f}° "
      f"p90 {np.percentile(angs,90):.2f}°)")
print(f"深度范围 中位 lo={np.median(drange[:,0]):.2f}m hi={np.median(drange[:,1]):.2f}m")

# ── 相机表(36 float/帧,与既有 C++ 载具约定一致)──
cams = np.zeros((NF, 36), np.float32)
for i in range(NF):
    cams[i, 0:9] = Ks[i].reshape(-1)
    cams[i, 9:18] = Rs[i].reshape(-1)
    cams[i, 18:21] = ts[i]
    cams[i, 21:24] = Cs[i]
    cams[i, 24], cams[i, 25] = drange[i]
    cams[i, 26], cams[i, 27] = W, H
cams.tofile(f"{OUT}/cams.f32")

# ── 图像:灰度 f16(给现有载具)+ RGB(给真彩上色)──
os.makedirs(f"{OUT}/rgb", exist_ok=True)
imgs = np.zeros((NF, H, W), np.float16)
for i, n in enumerate(names):
    im = Image.open(f"{O}/photos_jpg/{n}").convert("RGB").resize((W, H), Image.BILINEAR)
    im.save(f"{OUT}/rgb/{i:08d}.jpg", quality=95)
    imgs[i] = (np.asarray(im.convert("L"), np.float32)/255.0).astype(np.float16)
    if i % 25 == 0:
        print(f"  解码 {i}/{NF}", flush=True)
imgs.tofile(f"{OUT}/images.f16")

json.dump({"count": int(NF), "width": W, "height": H, "num_src": NSRC,
           "source": os.path.basename(O),
           "names": names,
           "frame_ids": [int(p["frame_id"]) for p in poses],
           "drange": drange.tolist(),
           "pose_convention": "refined COLMAP/OpenCV axes (投影实测判定,未补 diag(1,-1,-1))"},
          open(f"{OUT}/frames.json", "w"), ensure_ascii=False)
print(f"→ {OUT}/  images.f16({imgs.nbytes/1e6:.0f}MB) cams.f32 neighbors.i32 frames.json rgb/")
