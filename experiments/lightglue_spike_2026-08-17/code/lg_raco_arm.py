#!/usr/bin/env python3
"""臂 R:RaCo 检测器 + ALIKED 描述子 + raco-aliked LightGlue 权重。

与 B2 的**唯一**差别是前端换人:
  B2:ALIKED 的 DKD 检测器 → ALIKED SDDH 描述子 → aliked_lightglue.pth
  R :RaCo  的检测头       → ALIKED SDDH 描述子 → raco_aliked_lightglue.pth
描述子头是同一份 aliked-n16 权重,所以这一臂量的就是"换检测器 + 换匹配器权重"。

⚠️ 排序器(ranker):上游自己的 RankerMode.auto 在 num_keypoints ≥ 3072 时解析成
`bypass` —— 也就是说在我们的 8192 预算下,上游的实测结论是排序器不该开。
默认因此走 bypass(只按检测分取前 8192),与我导出的那份 ONNX 一致;
--ranker dense 可以把它打开做对照。

⚠️ 尺寸:RaCo 主干里有 scale_factor=32 的上采样再 cat,长宽必须被 32 整除。
4032×3024 按长边 1600 缩放会得到 1600×1200(1200 不整除)⇒ 取 1600×1216,
与上游导出用的 -h 1216 -w 1600 一致。关键点回写原图坐标时按 x/y 各自的比例
反算,这点各向异性会精确抵消。
"""
import argparse, json, shutil, sqlite3, sys, time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import devutil
import lg_load  # 必须先于 lightglue 子模块(装 kornia 桩 + 绕开 pycolmap)
import chunked_attn
import chunked_assign

sys.path.insert(0, str(Path(__file__).parent / "LightGlue-ONNX"))

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--frame-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--long-side", type=int, default=1600)
    ap.add_argument("--max-kpts", type=int, default=8192)
    ap.add_argument("--ranker", default="bypass", choices=["bypass", "dense"])
    ap.add_argument("--select", default="score", choices=["score", "cov"],
                    help="选点判据。score=按检测分取前 K(现状);"
                         "cov=多取候选后只留协方差头判定**定位最确定**的 K 个 —— "
                         "RaCo 的 Co 就是 covariance,这个头一直被 dynamo 的加载器丢掉")
    ap.add_argument("--cand-mult", type=float, default=2.0,
                    help="--select cov 时的候选倍数(取 mult×K 个候选,留 σ 最小的 K 个)")
    ap.add_argument("--raco-weights", default=None,
                    help="raco.pth 路径(默认从 torch hub 缓存找)")
    ap.add_argument("--pairs", type=int, default=0)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--depth-conf", type=float, default=-1.0,
                    help="LightGlue 自带自适应深度。−1=关。上手机必开:剪枝是唯一"
                         "满足三端约束的真提速(1.566×,重建层近乎无损)")
    ap.add_argument("--width-conf", type=float, default=-1.0,
                    help="LightGlue 自带自适应宽度(逐层剪点)。−1=关")
    ap.add_argument("--attn-chunk", type=int, default=1024)
    ap.add_argument("--assign-chunk", type=int, default=1024)
    args = ap.parse_args()

    from lightglue_dynamo.config import RankerMode
    from lightglue_dynamo.models.aliked import RaCoALIKED

    utils = lg_load.load("utils")
    lg_mod = lg_load.load("lightglue")
    dev = torch.device(args.device)
    devutil.strict_fp32()

    mode = RankerMode.bypass if args.ranker == "bypass" else RankerMode.dense
    extractor = RaCoALIKED(
        num_keypoints=args.max_kpts,
        # dense 档给 2× 候选池才让排序器真有得选;bypass 档池=输出,多取无意义
        max_num_candidates=None if args.ranker == "dense" else args.max_kpts,
        sort_by_ranker=(args.ranker == "dense"),
        ranker_mode=mode,
        # 🔴 必须关掉上游的分块 topk:MPS 上 topk 作用在「绝大多数是 −inf」的分块
        #    张量上会整块返回 −inf(实测 [1,30,65536]、每块仅 ~975 个有限值 ⇒ 有限值
        #    0 个存活),于是关键点全落在第 0 行(y 只在 0–2px)、匹配数恒为 0。
        #    展平后的直接 topk 在 MPS 上结果与 CPU 逐条相同,而分块本来就只是
        #    上游为 TensorRT 延迟做的等价改写 ⇒ 走回退路径不损精度。
        topk_chunk_size=None,
    ).eval().to(dev)

    if args.attn_chunk:
        chunked_attn.patch(lg_mod, args.attn_chunk)
    if args.assign_chunk:
        chunked_assign.patch(lg_mod, args.assign_chunk)
    cov_head = None
    if args.select == "cov":
        import raco_cov
        wp = args.raco_weights or (Path.home() / ".cache/torch/hub/checkpoints/raco.pth")
        cov_head = raco_cov.load_head(wp).to(dev)
        n_cand = max(args.max_kpts, int(args.max_kpts * args.cand_mult))
        print(f"协方差选点:候选 {n_cand} → 留 σ 最小的 {args.max_kpts}", flush=True)

    matcher = lg_mod.LightGlue(features="raco-aliked",
                               depth_confidence=args.depth_conf,
                               width_confidence=args.width_conf).eval().to(dev)
    print(f"RaCo({args.ranker}) + ALIKED-desc + raco-aliked LightGlue @ {dev}", flush=True)

    db = sqlite3.connect(args.db)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    base = {p: r for p, r in db.execute("select pair_id,rows from matches")}
    db.close()
    if args.pairs:
        step = max(1, len(pairs) // args.pairs)
        pairs = pairs[::step][:args.pairs]

    imgdir = Path(args.images)
    fmap = json.load(open(args.frame_map))
    feats, kp32_store, t_ex = {}, {}, 0.0
    sig_all, sig_keep = [], []
    for k, (iid, nm) in enumerate(sorted(names.items())):
        p = imgdir / fmap[str(iid)]
        if not p.exists():
            raise FileNotFoundError(f"{nm} → {p} 不存在")
        img = utils.load_image(str(p)).to(dev)          # [3,H,W] float 0-1 RGB
        H, W = img.shape[-2:]
        s = args.long_side / max(H, W)
        th = max(32, int(round(H * s / 32)) * 32)
        tw = max(32, int(round(W * s / 32)) * 32)
        t0 = time.perf_counter()
        with torch.no_grad():
            im = F.interpolate(img[None], size=(th, tw), mode="bilinear",
                               align_corners=False, antialias=True)
            if cov_head is None:
                kp, de = extractor.extract_for_matching(im)   # kp:[1,N,2] 缩放帧像素
            else:
                import raco_cov
                # 上游那条候选路径原样用(保真),再单独跑一遍主干喂协方差头
                nimg, cand, _lg = extractor.raco._candidate_keypoints(im, n_cand)
                cand = cand + 0.5
                chol = raco_cov.sample_at(
                    raco_cov.cholesky_maps(cov_head, raco_cov.dense_features(extractor.raco, nimg)),
                    cand)
                sig = raco_cov.sigma_from_cholesky(chol)      # [1,N]
                keep = sig.topk(args.max_kpts, dim=1, largest=False).indices
                sig_all.append(sig[0].float().cpu())
                sig_keep.append(sig.gather(1, keep)[0].float().cpu())
                kp = cand.gather(1, keep[..., None].expand(-1, -1, 2))
                de = extractor.aliked(im, kp)
        devutil.sync(dev)
        t_ex += time.perf_counter() - t0
        # 回写原图坐标(x、y 各自的比例,抵消 1200→1216 那点纵向拉伸)
        kp_orig = kp[0].float().cpu() * torch.tensor([W / tw, H / th])
        kp32_store[iid] = kp_orig
        feats[iid] = {"keypoints": kp_orig.to(dev)[None][0],
                      "descriptors": de[0],
                      "image_size": torch.tensor([float(W), float(H)], device=dev)}
        del img, im, kp, de
        if (k + 1) % 20 == 0:
            print(f"  提取 {k+1}/{len(names)}  累计 {t_ex:.0f}s", flush=True)
    n_kp = np.mean([v["keypoints"].shape[0] for v in feats.values()])
    print(f"提取完成:{len(feats)} 帧,平均 {n_kp:.0f} 关键点,"
          f"{t_ex/len(feats)*1000:.0f} ms/帧", flush=True)
    if sig_all:
        a = torch.cat(sig_all).numpy(); k = torch.cat(sig_keep).numpy()
        # σ 的分布必须先看:如果候选与留下的几乎一样,说明这个头没给出可用信号
        print(f"σ(候选 {len(a):,}) 分位 p10 {np.percentile(a,10):.4f} "
              f"中位 {np.median(a):.4f} p90 {np.percentile(a,90):.4f} 最大 {a.max():.4f}",
              flush=True)
        print(f"σ(留下 {len(k):,}) 中位 {np.median(k):.4f} 最大 {k.max():.4f}  "
              f"⇒ 判据区分度 {np.median(a)/max(np.median(k),1e-9):.3f}×(≈1 就是没信号)",
              flush=True)

    out_rows, t_m, n_lg, n_base = [], 0.0, 0, 0
    stops = []
    for i, pid in enumerate(pairs):
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if i1 not in feats or i2 not in feats:
            continue
        d = {"image%d" % j: {k: v[None] for k, v in feats[x].items()}
             for j, x in ((0, i1), (1, i2))}
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = matcher(d)
        devutil.sync(dev)
        t_m += time.perf_counter() - t0
        m = pred["matches"][0].cpu().numpy().astype(np.uint32)
        out_rows.append((pid, m))
        stops.append(int(pred["stop"]))
        n_lg += len(m); n_base += base.get(pid, 0)
        if i < 3 or (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(pairs)}] LG={len(m):5d} base={base.get(pid,0):5d} "
                  f"{(time.perf_counter()-t0)*1000:7.1f}ms", flush=True)

    k = len(out_rows)
    print(f"\n=== {k} 对 ===")
    print(f"RaCo+ALIKED+LightGlue 平均 {n_lg/k:8.1f} 匹配/对")
    print(f"基线(DSP-SIFT 暴力+0.8) 平均 {n_base/k:8.1f}")
    print(f"比值 {n_lg/max(n_base,1):.3f}×    匹配 {t_m/k*1000:.1f} ms/对")
    print(f"自适应深度:平均在第 {np.mean(stops):.2f}/9 层停(9=跑满),"
          f"分布 {np.bincount(stops, minlength=10)[1:].tolist()}")

    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(args.out)
    o.execute("delete from keypoints"); o.execute("delete from descriptors")
    o.execute("delete from matches");   o.execute("delete from two_view_geometries")
    for iid in feats:
        kp = kp32_store[iid].numpy().astype(np.float32)
        o.execute("insert into keypoints(image_id,rows,cols,data) values(?,?,?,?)",
                  (iid, kp.shape[0], 2, kp.tobytes()))
    for pid, m in out_rows:
        o.execute("insert into matches(pair_id,rows,cols,data) values(?,?,?,?)",
                  (pid, m.shape[0], 2, m.tobytes()))
    o.commit(); o.close()
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
