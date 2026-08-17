#!/usr/bin/env python3
"""交替 A/B 探针:LightGlue 自带自适应剪枝 vs B2(剪枝全关)。

为什么不是直接跑满 1516 对:单场跑一次再跑一次,量到的差异里混着机器漂移
(我们自己的旧账:单场对比噪声地板 18% > 效应)。这里**同一进程、同一份特征、
逐对交替**跑两种配置,并且每对内部交换先后顺序,把预热和漂移都摊掉。

三件事一起量:
  1. 速度:剪枝 vs 不剪枝,逐对配对比时间
  2. 无损与否:两者匹配集合的 Jaccard(以及各自与 b28_armB2.db 存档的一致性)
  3. 剪到哪:平均在第几层提前退出

⚠️ MPS 缓存池:剪枝让每层张量形状逐对变化,缓存分配器复用不了块 ⇒ 池子无界涨。
   不设闸时实测 swap 冲到 14.3GB、单对从 3.5s 退化到 ~10s —— 那时量到的是换页,
   不是算法。这里超过 --pool-cap-gb 就 empty_cache,并把 flush 次数打出来。
"""
import argparse, sqlite3, time
from pathlib import Path

import numpy as np
import torch

import devutil
import lg_load

MAX_IMAGE_ID = 2147483647


def match_set(m):
    return set(map(tuple, m.tolist()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="b28_src.db")
    ap.add_argument("--ref-db", default="b28_armB2.db", help="B2 存档,用来验证未剪枝路径可复现")
    ap.add_argument("--images", default="frames")
    ap.add_argument("--frame-map", default="b28_frame_map.json")
    ap.add_argument("--pairs", type=int, default=40)
    ap.add_argument("--resize", type=int, default=1600)
    ap.add_argument("--max-kpts", type=int, default=8192)
    ap.add_argument("--det-thr", type=float, default=0.02)
    ap.add_argument("--pool-cap-gb", type=float, default=6.0)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    utils = lg_load.load("utils")
    aliked_mod = lg_load.load("aliked")
    lg_mod = lg_load.load("lightglue")
    dev = torch.device(args.device)
    devutil.strict_fp32()

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    db.close()
    step = max(1, len(pairs) // args.pairs)
    pairs = pairs[::step][:args.pairs]
    need = sorted({i for p in pairs for i in (p // MAX_IMAGE_ID, p % MAX_IMAGE_ID)})

    ref = sqlite3.connect(f"file:{args.ref_db}?mode=ro", uri=True)

    import json
    fmap = json.load(open(args.frame_map))
    extractor = aliked_mod.ALIKED(max_num_keypoints=args.max_kpts,
                                  detection_threshold=args.det_thr).eval().to(dev)
    feats = {}
    for iid in need:
        img = utils.load_image(str(Path(args.images) / fmap[str(iid)])).to(dev)
        with torch.no_grad():
            f = extractor.extract(img, resize=args.resize)
        feats[iid] = {"keypoints": f["keypoints"][0], "descriptors": f["descriptors"][0],
                      "image_size": f["image_size"][0]}
        del img, f
    devutil.sync(dev)
    del extractor
    devutil.empty(dev)
    print(f"提取完成 {len(feats)} 帧(仅探针需要的),池={devutil.pool_gb(dev):.2f}GB",
          flush=True)

    matchers = {
        "OFF": lg_mod.LightGlue(features="aliked", depth_confidence=-1,
                                width_confidence=-1).eval().to(dev),
        "ON": lg_mod.LightGlue(features="aliked", depth_confidence=0.95,
                               width_confidence=0.99).eval().to(dev),
    }

    def run(tag, pid):
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        d = {"image%d" % j: {k: v[None] for k, v in feats[x].items()}
             for j, x in ((0, i1), (1, i2))}
        devutil.sync(dev)
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = matchers[tag](d)
        devutil.sync(dev)
        dt = time.perf_counter() - t0
        return dt, pred["matches"][0].cpu().numpy(), int(pred["stop"])

    # 预热:两条路径各跑一次,不计入
    for tag in ("OFF", "ON"):
        run(tag, pairs[0])

    rows, n_flush = [], 0
    for k, pid in enumerate(pairs):
        order = ("OFF", "ON") if k % 2 == 0 else ("ON", "OFF")   # 逐对交换先后
        res = {}
        for tag in order:
            res[tag] = run(tag, pid)
        r = ref.execute("select rows,data from matches where pair_id=?", (pid,)).fetchone()
        ref_m = np.frombuffer(r[1], dtype=np.uint32).reshape(r[0], 2) if r else None
        s_off, s_on = match_set(res["OFF"][1]), match_set(res["ON"][1])
        s_ref = match_set(ref_m) if ref_m is not None else None
        rows.append(dict(
            pid=pid, t_off=res["OFF"][0], t_on=res["ON"][0],
            n_off=len(s_off), n_on=len(s_on), stop=res["ON"][2],
            jac=len(s_off & s_on) / max(len(s_off | s_on), 1),
            recall=len(s_off & s_on) / max(len(s_off), 1),
            ref_ok=(None if s_ref is None else len(s_off & s_ref) / max(len(s_off | s_ref), 1)),
        ))
        pool = devutil.pool_gb(dev)
        if pool > args.pool_cap_gb:
            devutil.empty(dev); n_flush += 1
        if (k + 1) % 10 == 0:
            print(f"  [{k+1}/{len(pairs)}] 池={pool:.2f}GB flush={n_flush}", flush=True)

    ref.close()
    t_off = np.array([r["t_off"] for r in rows]) * 1000
    t_on = np.array([r["t_on"] for r in rows]) * 1000
    print(f"\n=== {len(rows)} 对交替 A/B ===")
    print(f"剪枝关(=B2)  中位 {np.median(t_off):7.1f} ms/对   均值 {t_off.mean():7.1f}")
    print(f"剪枝开        中位 {np.median(t_on):7.1f} ms/对   均值 {t_on.mean():7.1f}")
    sp = t_off / t_on
    print(f"逐对加速比    中位 {np.median(sp):.3f}×  p10 {np.percentile(sp,10):.3f}  "
          f"p90 {np.percentile(sp,90):.3f}   (>1 才是变快)")
    print(f"提前退出层    中位 {np.median([r['stop'] for r in rows]):.1f}/9  "
          f"分布 {np.bincount([r['stop'] for r in rows], minlength=10)[1:].tolist()}")
    print(f"匹配数        关 {np.mean([r['n_off'] for r in rows]):.0f}  "
          f"开 {np.mean([r['n_on'] for r in rows]):.0f}  "
          f"({np.mean([r['n_on'] for r in rows])/np.mean([r['n_off'] for r in rows]):.3f}×)")
    print(f"匹配集合 Jaccard(开 vs 关) 中位 {np.median([r['jac'] for r in rows]):.4f}  "
          f"最低 {min(r['jac'] for r in rows):.4f}")
    print(f"关掉剪枝的匹配被保留的比例  中位 {np.median([r['recall'] for r in rows]):.4f}")
    ro = [r["ref_ok"] for r in rows if r["ref_ok"] is not None]
    if ro:
        print(f"自检:未剪枝路径 vs b28_armB2.db 存档 Jaccard 中位 {np.median(ro):.4f} "
              f"(应≈1.0000,否则说明特征没复现出来)")
    print(f"MPS 池 flush 次数 {n_flush}")


if __name__ == "__main__":
    main()
