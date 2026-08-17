#!/usr/bin/env python3
"""SIFT + LightGlue 臂:沿用真机 DSP-SIFT 描述子,只换"对内怎么匹配"。

严格单变量:关键点、描述子、配对表全部取自真机 session.db,唯一变化是
brute-force + Lowe ratio 0.8  →  LightGlue(sift 权重)。

约定对齐(易踩空,见 lightglue/utils.py:146):
  · keypoints 喂原图像素,forward 内部按 image_size 归一化 ⇒ 分辨率无关
  · scales    官方留在 resize=1024 长边帧的**裸像素**里,直接拼进位置编码
              ⇒ 我们必须乘 1024/max(W,H),否则落到分布外。--scale-mode 可关掉验证
  · oris      弧度
  · descriptors RootSIFT(L1→clip→sqrt→L2)。COLMAP uint8 = round(512·d),
              故 /512 后再 L2 归一化即可对上。
"""
import argparse, importlib.util, math, sqlite3, struct, sys, time
from pathlib import Path

import numpy as np
import torch

import devutil

HERE = Path(__file__).resolve().parent
MAX_IMAGE_ID = 2147483647


def load_lightglue():
    """直接按文件加载 lightglue/lightglue.py,绕开 __init__.py 的 kornia/cv2 依赖。"""
    p = HERE / "LightGlue" / "lightglue" / "lightglue.py"
    spec = importlib.util.spec_from_file_location("lg_matcher", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lg_matcher"] = mod
    spec.loader.exec_module(mod)
    return mod.LightGlue


def blob(b, dtype, cols):
    a = np.frombuffer(b, dtype=dtype)
    return a.reshape(-1, cols)


def pair_id_to_images(pid):
    return pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID


def images_to_pair_id(a, b):
    if a > b:
        a, b = b, a
    return a * MAX_IMAGE_ID + b


def read_features(db, scale_mode, device):
    """image_id -> dict(kpts, scales, oris, desc),已按约定转换好。"""
    cams = {cid: (w, h) for cid, w, h in db.execute("select camera_id,width,height from cameras")}
    img_cam = {iid: cid for iid, cid in db.execute("select image_id,camera_id from images")}

    kp_raw = {iid: blob(d, np.float32, c) for iid, r, c, d in
              db.execute("select image_id,rows,cols,data from keypoints")}
    de_raw = {iid: blob(d, np.uint8, c) for iid, r, c, d in
              db.execute("select image_id,rows,cols,data from descriptors")}

    feats = {}
    for iid, kp in kp_raw.items():
        w, h = cams[img_cam[iid]]
        assert kp.shape[1] == 6, f"期望 6 列仿射 keypoint,得到 {kp.shape[1]}"
        x, y = kp[:, 0], kp[:, 1]
        a11, a12, a21, a22 = kp[:, 2], kp[:, 3], kp[:, 4], kp[:, 5]
        # COLMAP FeatureKeypoint::ComputeScaleX / ComputeOrientation
        scale = np.sqrt(a11 * a11 + a21 * a21)
        ori = np.arctan2(a21, a11)
        if scale_mode == "rescaled":
            scale = scale * (1024.0 / max(w, h))

        d = de_raw[iid].astype(np.float32) / 512.0
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-8

        feats[iid] = {
            "keypoints": torch.from_numpy(np.stack([x, y], 1)).to(device),
            "scales": torch.from_numpy(scale.copy()).to(device),
            "oris": torch.from_numpy(ori.copy()).to(device),
            "descriptors": torch.from_numpy(d).to(device),
            "image_size": torch.tensor([float(w), float(h)]).to(device),
        }
    return feats


def pack(feat, n=None):
    """加 batch 维;n 不为空时截断到前 n 个点。"""
    sl = slice(None) if n is None else slice(0, n)
    return {
        "keypoints": feat["keypoints"][sl][None],
        "scales": feat["scales"][sl][None],
        "oris": feat["oris"][sl][None],
        "descriptors": feat["descriptors"][sl][None],
        "image_size": feat["image_size"][None],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--pairs", type=int, default=0, help="0=全部")
    ap.add_argument("--kpts", type=int, default=0, help="0=全部(生产 8192)")
    ap.add_argument("--scale-mode", choices=["rescaled", "raw"], default="rescaled")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--depth-confidence", type=float, default=-1, help="-1=关自适应深度")
    ap.add_argument("--width-confidence", type=float, default=-1)
    args = ap.parse_args()

    dev = torch.device(args.device)
    devutil.strict_fp32()
    LightGlue = load_lightglue()
    matcher = LightGlue(features="sift",
                        depth_confidence=args.depth_confidence,
                        width_confidence=args.width_confidence).eval().to(dev)
    print(f"LightGlue(sift) 就绪 @ {dev}, scale-mode={args.scale_mode}", flush=True)

    db = sqlite3.connect(args.db)
    feats = read_features(db, args.scale_mode, dev)
    pairs = [pid for (pid,) in db.execute("select pair_id from matches order by pair_id")]
    base = {pid: r for pid, r in db.execute("select pair_id,rows from matches")}
    db.close()
    if args.pairs:
        # 均匀抽样,避免只取到序号相邻的易配对
        step = max(1, len(pairs) // args.pairs)
        pairs = pairs[::step][:args.pairs]
    print(f"配对 {len(pairs)} 对,关键点上限 {args.kpts or '全部'}", flush=True)

    n = args.kpts or None
    out_rows, t_total, n_lg, n_base = [], 0.0, 0, 0
    for i, pid in enumerate(pairs):
        i1, i2 = pair_id_to_images(pid)
        if i1 not in feats or i2 not in feats:
            continue
        d = {"image0": pack(feats[i1], n), "image1": pack(feats[i2], n)}
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = matcher(d)
        if dev.type == "mps":
            devutil.sync(dev)
        dt = time.perf_counter() - t0
        t_total += dt

        m = pred["matches"][0].cpu().numpy()  # [K,2] 索引对
        out_rows.append((pid, m.astype(np.uint32)))
        n_lg += len(m)
        n_base += base.get(pid, 0)
        if i < 5 or (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(pairs)}] pair({i1},{i2}) "
                  f"LG={len(m):5d}  base={base.get(pid,0):5d}  {dt*1000:7.1f}ms", flush=True)

    k = len(out_rows)
    print(f"\n=== {k} 对 ===")
    print(f"LightGlue 平均 {n_lg/k:8.1f} 匹配/对")
    print(f"基线(暴力+0.8) 平均 {n_base/k:8.1f} 匹配/对")
    print(f"比值 {n_lg/max(n_base,1):.3f}×")
    print(f"耗时 平均 {t_total/k*1000:.1f} ms/对   合计 {t_total:.1f}s")

    if args.out:
        import shutil
        shutil.copy(args.db, args.out)
        for suf in ("-wal", "-shm"):
            Path(args.out + suf).unlink(missing_ok=True)
        o = sqlite3.connect(args.out)
        o.execute("delete from matches")
        o.execute("delete from two_view_geometries")
        for pid, m in out_rows:
            o.execute("insert into matches(pair_id,rows,cols,data) values(?,?,?,?)",
                      (pid, m.shape[0], 2, m.tobytes()))
        o.commit()
        o.close()
        print(f"已写出 {args.out}(matches 重写,TVG 已清空待重验)")


if __name__ == "__main__":
    main()
