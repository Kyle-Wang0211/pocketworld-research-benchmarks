#!/usr/bin/env python3
"""ALIKED + 极线门控匹配臂 —— 「AR 位姿 + 描述子」能不能顶替 LightGlue 的 transformer。

BF16K 臂(无门暴力互检)已判:494 匹配/对,只有 LightGlue 的 1/9.2 ⇒ 无先验时
transformer 的上下文精炼是真功劳。但 ratio 检验的职责是"在 16384 个候选里拒绝歧义",
而极线门把候选压到 ~0.18%(约 30 个),歧义在几何上直接消解 ⇒ 门内可以放开 ratio。

本臂:sim 矩阵先按极线带(|点到极线| < tol px)置 -inf,再做互检;ratio 默认放宽到 0.95。
位姿来自 poses_P16k.npz(生产等价物 = ARKit 位姿,更糙,所以 tol 要留余量)。

臂A(SIFT+LightGlue)拆的是"同样的点换匹配器";本臂是反方向:"同样的点**不换**匹配器"。
提取与 P16kH 完全相同(fp16 autocast / resize / det-thr / max-kpts),唯一变量是匹配器:
LightGlue(9 层 transformer)→ 暴力互检 + Lowe ratio 0.8(与生产基线同语义)。

匹配语义(对齐生产 DSP-SIFT 暴力匹配):
  sim = D1 @ D2^T(ALIKED 描述子是 L2 归一化的,点积=余弦)
  L2² = 2 − 2·sim ⇒ ratio 检验 d1/d2 < 0.8 等价于 (2−2s1) < 0.64·(2−2s2)
  互检:i→j 且 j→i 同为最近邻才保留。

顺带这也是「极线门暴力匹配」的第一步:如果无门的暴力匹配就守得住重建层质量,
再加 AR 位姿极线门只会更好(候选点级只有 0.18% 在带内)。
"""
import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path

import numpy as np
import torch

import devutil
import lg_load  # 按需加载器:绕开 lightglue/__init__(它拉 pycolmap → libomp 冲突 abort)

utils = lg_load.load("utils")
_aliked_mod = lg_load.load("aliked")
ALIKED = _aliked_mod.ALIKED

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--frame-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resize", type=int, default=1600)
    ap.add_argument("--max-kpts", type=int, default=16384)
    ap.add_argument("--det-thr", type=float, default=0.02)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--extract-amp", action="store_true")
    ap.add_argument("--ratio", type=float, default=0.95,
                    help="门内歧义已被几何消解,ratio 只挡近重复纹理,可放宽")
    ap.add_argument("--poses", default="poses_P16k.npz")
    ap.add_argument("--tol", type=float, default=6.0,
                    help="极线带半宽(px)。AR 位姿比重建位姿糙,给 6 不给 3")
    a = ap.parse_args()

    z = np.load(a.poses)
    pid2idx = {int(i): k for k, i in enumerate(z["ids"])}
    PK, PR, PT = z["K"], z["R"], z["t"]

    dev = torch.device(a.device)
    ext = ALIKED(model_name="aliked-n16", max_num_keypoints=a.max_kpts,
                 detection_threshold=a.det_thr).eval().to(dev)
    print(f"ALIKED(resize={a.resize}, max={a.max_kpts}, "
          f"提取{'fp16' if a.extract_amp else 'fp32'}) + 暴力互检 ratio {a.ratio} @ {dev}",
          flush=True)

    db = sqlite3.connect(a.db)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    base = {p: r for p, r in db.execute("select pair_id,rows from matches")}
    db.close()

    # ---- 提取:与 lg_aliked_arm.py 逐行同口径 ----
    imgdir = Path(a.images)
    fmap = json.load(open(a.frame_map))
    feats, kp32_store, t_ex = {}, {}, 0.0
    for k, (iid, nm) in enumerate(sorted(names.items())):
        p = imgdir / fmap[str(iid)]
        img = utils.load_image(str(p)).to(dev)
        t0 = time.perf_counter()
        with torch.no_grad():
            if a.extract_amp:
                with torch.autocast(device_type=dev.type, dtype=torch.float16):
                    f = ext.extract(img, resize=a.resize)
                f = {k2: (v.float() if torch.is_floating_point(v) else v)
                     for k2, v in f.items()}
            else:
                f = ext.extract(img, resize=a.resize)
        devutil.sync(dev)
        t_ex += time.perf_counter() - t0
        kp32_store[iid] = f["keypoints"][0].float().cpu()
        # 描述子留在 GPU 转 half:16384×128×2B = 4MB/帧,132 帧才 0.5GB
        feats[iid] = f["descriptors"][0].half()
        del img, f
        if (k + 1) % 40 == 0:
            print(f"  提取 {k+1}/{len(names)}", flush=True)
    n_kp = np.mean([v.shape[0] for v in feats.values()])
    print(f"提取完成:{len(feats)} 帧,平均 {n_kp:.0f} 关键点,"
          f"{t_ex/len(feats)*1000:.0f} ms/帧", flush=True)

    # ---- 暴力互检 + ratio ----
    r2 = a.ratio * a.ratio
    out_rows, t_m, n_bf, n_base = [], 0.0, 0, 0
    for i, pid in enumerate(pairs):
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if i1 not in feats or i2 not in feats:
            continue
        D1, D2 = feats[i1], feats[i2]
        a1, a2 = pid2idx.get(i1), pid2idx.get(i2)
        t0 = time.perf_counter()
        with torch.no_grad():
            sim = D1 @ D2.T                            # [N1,N2] fp16
            if a1 is not None and a2 is not None:
                # F = K2^-T [t]x R K1^-1(P16k 位姿;生产用 ARKit 位姿同式)
                R_ = PR[a2] @ PR[a1].T
                t_ = PT[a2] - R_ @ PT[a1]
                tx = np.array([[0, -t_[2], t_[1]], [t_[2], 0, -t_[0]], [-t_[1], t_[0], 0]])
                F = np.linalg.inv(PK[a2]).T @ tx @ R_ @ np.linalg.inv(PK[a1])
                Ft = torch.from_numpy(F).float().to(dev)
                x1 = kp32_store[i1].to(dev); x2 = kp32_store[i2].to(dev)
                h1 = torch.cat([x1, torch.ones(len(x1), 1, device=dev)], 1)
                h2 = torch.cat([x2, torch.ones(len(x2), 1, device=dev)], 1)
                lines = h1 @ Ft.T
                nrm = lines[:, :2].norm(dim=1, keepdim=True).clamp_min(1e-9)
                dist = (lines @ h2.T).abs() / nrm
                sim = sim.masked_fill((dist > a.tol).to(sim.dtype).bool(), float("-inf"))
            top2 = sim.topk(2, dim=1)                  # 1→2 最近与次近
            s1, s2 = top2.values[:, 0].float(), top2.values[:, 1].float()
            nn12 = top2.indices[:, 0]
            nn21 = sim.argmax(dim=0)                   # 2→1 最近
            idx = torch.arange(D1.shape[0], device=dev)
            mutual = nn21[nn12] == idx
            # Lowe ratio(L2 语义):d1²< r²·d2² ⇔ 2−2s1 < r²·(2−2s2)
            ratio_ok = (2 - 2 * s1) < r2 * (2 - 2 * s2)
            keep = mutual & ratio_ok
        devutil.sync(dev)
        t_m += time.perf_counter() - t0
        m = torch.stack([idx[keep], nn12[keep]], 1).cpu().numpy().astype(np.uint32)
        out_rows.append((pid, m))
        n_bf += len(m); n_base += base.get(pid, 0)
        if i < 3 or (i + 1) % 300 == 0:
            print(f"  [{i+1}/{len(pairs)}] BF={len(m):5d} base={base.get(pid,0):5d} "
                  f"{(time.perf_counter()-t0)*1000:6.1f}ms", flush=True)

    k = len(out_rows)
    print(f"\n=== {k} 对 ===")
    print(f"ALIKED+极线门互检   平均 {n_bf/k:8.1f} 匹配/对")
    print(f"基线(SIFT 暴力+0.8) 平均 {n_base/k:8.1f}")
    print(f"比值 {n_bf/max(n_base,1):.3f}×    匹配 {t_m/k*1000:.2f} ms/对", flush=True)

    # ---- 写库:与 lg_aliked_arm.py 相同 ----
    shutil.copy(a.db, a.out)
    for suf in ("-wal", "-shm"):
        Path(a.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(a.out)
    o.execute("delete from keypoints"); o.execute("delete from descriptors")
    o.execute("delete from matches");   o.execute("delete from two_view_geometries")
    for iid in kp32_store:
        kp = kp32_store[iid].numpy().astype(np.float32)
        o.execute("insert into keypoints(image_id,rows,cols,data) values(?,?,?,?)",
                  (iid, kp.shape[0], 2, kp.tobytes()))
    for pid, m in out_rows:
        o.execute("insert into matches(pair_id,rows,cols,data) values(?,?,?,?)",
                  (pid, m.shape[0], 2, m.tobytes()))
    o.commit(); o.close()
    print(f"已写出 {a.out}")


if __name__ == "__main__":
    main()
