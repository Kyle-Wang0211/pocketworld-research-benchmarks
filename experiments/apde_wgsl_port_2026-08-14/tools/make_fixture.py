#!/usr/bin/env python3
"""单帧闭环 fixture 生成器:npz 素材 → Metal 载具能吃的二进制。

用法:
    python3 make_fixture.py <ref_frame_idx> <out_dir>

产出(全部 little-endian):
    meta.json        参数与形状
    cams.bin         5 个 Camera(144 B/个,与 apde_common.wgsl 逐字段一致)
    img_<i>.f16      5 张灰度图,896×512,RGBA16F(R=G=B=灰度, A=1)

⚠️ 分辨率的坑(实测确认,别改):
   照片是 4224×2376(16:9),但 K 的 cx=448/cy=256 且 fy/fx=1.0159=512/504,
   说明 K 编码的是**非等比**缩放到 896×512。若按保持宽高比缩到 896×504,
   垂直方向最多错 8 像素,NCC 直接废掉。
   验证方法:把稀疏点投影进来看 v 的范围 —— 实测到 511.0,证明高度是 512。
"""
import sys, os, json, struct
import numpy as np
from PIL import Image

R = os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks")
MODEL = f"{R}/tools/python/diffmvs_out/trio_model_lapa.npz"
PHOTOS = (f"{R}/data/official_da3_base_k35_strict_seq_2026_06_02/"
          f"capture_seq_k35_strict/photos_highres")
W, H = 896, 512
NUM_SRC = 4                      # 对应 APDe 的 num_images=5(1 参考 + 4 源)


def f32_to_f16(a):
    return a.astype(np.float16)


def pick_sources(ref, obs_idx, obs_off, pts, centers, n=NUM_SRC):
    """按 COLMAP 式打分选源视图:共视点数 × 三角化角的高斯权。

    🔴 初版只按共视点数排,选出来的是紧邻的近重复帧 —— 实测基线只有
       0.04–0.10 m,4m 深度处视差角 **0.56°–1.37°**,远低于我们生产的
       交付门(视差角 ≥ 3°)。后果:NCC 代价很低(图长得像)但深度完全
       没有约束,深度图是噪声。单帧闭环第一次跑就是这么暴露的。

    现在用真实三角化角:对每个共视点算 ref 与 src 的视线夹角,取中位数,
    按 COLMAP 的做法用高斯加权(峰值 theta0),再乘共视点数。
    """
    THETA0 = 12.0     # 峰值角(度)。COLMAP 用 5°,我们场景更近,取大一点
    SIGMA  = 8.0
    nfr = len(obs_off) - 1
    ridx = obs_idx[obs_off[ref]:obs_off[ref + 1]]
    rset = set(ridx.tolist())
    Cr = centers[ref]
    scored = []
    for f in range(nfr):
        if f == ref:
            continue
        common = np.fromiter(rset & set(
            obs_idx[obs_off[f]:obs_off[f + 1]].tolist()), dtype=np.int64)
        if len(common) < 200:
            continue
        X = pts[common]
        v1 = X - Cr
        v2 = X - centers[f]
        v1 /= np.linalg.norm(v1, axis=1, keepdims=True) + 1e-12
        v2 /= np.linalg.norm(v2, axis=1, keepdims=True) + 1e-12
        ang = np.degrees(np.arccos(np.clip((v1 * v2).sum(1), -1, 1)))
        med = float(np.median(ang))
        w = np.exp(-((med - THETA0) ** 2) / (2 * SIGMA ** 2))
        scored.append((len(common) * w, med, len(common), f))
    scored.sort(reverse=True)
    sel = scored[:n]
    return ([x[3] for x in sel], [x[2] for x in sel], [x[1] for x in sel])


def cam_bytes(K, w2c, c, dmin, dmax, w, h):
    """打包成 apde_common.wgsl 的 Camera(144 B)。

    布局:K0/K1/K2/R0/R1/R2/t/c 各 vec4(16B) = 128B
          + depth_min/depth_max(f32×2)+ width/height(i32×2) = 16B
    """
    R3 = w2c[:3, :3]
    t3 = w2c[:3, 3]
    b = b""
    for row in K:                                   # K 行主序,每行补 pad
        b += struct.pack("<4f", row[0], row[1], row[2], 0.0)
    for row in R3:
        b += struct.pack("<4f", row[0], row[1], row[2], 0.0)
    b += struct.pack("<4f", t3[0], t3[1], t3[2], 0.0)
    b += struct.pack("<4f", c[0], c[1], c[2], 0.0)
    b += struct.pack("<2f2i", dmin, dmax, w, h)
    assert len(b) == 144, len(b)
    return b


def depth_range(frame, pts, obs_idx, obs_off, w2c):
    idx = obs_idx[obs_off[frame]:obs_off[frame + 1]]
    X = pts[idx]
    Xc = (w2c[frame][:3, :3] @ X.T).T + w2c[frame][:3, 3]
    d = Xc[:, 2]
    d = d[d > 0]
    # 用分位数而非 min/max,避免个别外点把范围撑爆
    lo, hi = np.percentile(d, [1, 99])
    return float(lo * 0.9), float(hi * 1.1)


def main():
    ref = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/apde_fixture"
    os.makedirs(out, exist_ok=True)

    z = np.load(MODEL, allow_pickle=True)
    names, K, w2c, centers = z["names"], z["K"], z["w2c"], z["centers"]
    pts, obs_idx, obs_off = z["pts"], z["obs_idx"], z["obs_off"]

    srcs, ov, angs = pick_sources(ref, obs_idx, obs_off, pts, centers)
    frames = [ref] + srcs
    print(f"参考帧 {ref} ({names[ref]})")
    for f, s, a in zip(srcs, ov, angs):
        b = float(np.linalg.norm(centers[ref] - centers[f]))
        print(f"  源视图 {f:>3} ({names[f]})  共视 {s:>5} 点  "
              f"基线 {b:5.3f} m  中位视差角 {a:5.2f}°")

    # 深度范围取参考帧的(APDe 的 params->depth_min/max 是全局的)
    dmin, dmax = depth_range(ref, pts, obs_idx, obs_off, w2c)
    print(f"深度范围 [{dmin:.3f}, {dmax:.3f}]")

    with open(f"{out}/cams.bin", "wb") as fh:
        for f in frames:
            fh.write(cam_bytes(K[f], w2c[f], centers[f], dmin, dmax, W, H))
        # 补齐到 32 个(WGSL 里 cams 是 array<Camera,32>)
        for _ in range(32 - len(frames)):
            fh.write(b"\0" * 144)

    for i, f in enumerate(frames):
        p = f"{PHOTOS}/{names[f]}"
        # ⚠️ 非等比缩放到 896×512,见文件头说明
        im = Image.open(p).convert("L").resize((W, H), Image.BILINEAR)
        g = (np.asarray(im, dtype=np.float32) / 255.0)
        rgba = np.stack([g, g, g, np.ones_like(g)], axis=-1)
        f32_to_f16(rgba).tofile(f"{out}/img_{i}.f16")

    json.dump({
        "ref_frame": int(ref), "ref_name": str(names[ref]),
        "src_frames": [int(x) for x in srcs],
        "src_names": [str(names[x]) for x in srcs],
        "overlap": [int(x) for x in ov],
        "tri_angle_deg": [float(x) for x in angs],
        "width": W, "height": H, "num_images": len(frames),
        "depth_min": dmin, "depth_max": dmax,
        "note": "K 编码非等比缩放到 896x512;照片原始 4224x2376",
    }, open(f"{out}/meta.json", "w"), indent=2, ensure_ascii=False)
    print(f"→ {out}/  (cams.bin + {len(frames)} 张 img_*.f16 + meta.json)")


if __name__ == "__main__":
    main()
