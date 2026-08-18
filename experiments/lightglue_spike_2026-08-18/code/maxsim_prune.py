#!/usr/bin/env python3
"""用"最大描述子相似度"在入口删点 —— 用便宜 200× 的 GEMM 给贵的 LightGlue 减负。

动机(逐层实测):剪枝要等一层注意力算完才有 matchability,所以**头两层是全额的**
(层0/1 各 0.76 TFLOP,N 仍占 97%,合计 42% 的算力)。而暴力 GEMM 只要 0.0172 TFLOP,
比 LightGlue 单对便宜 200×。

🔴 不能用 ratio test 筛 —— 那正好杀掉 LightGlue 相对暴力匹配的全部优势(4.76× 匹配)。
可以筛的是更弱的判据:**一个点若对另一图所有点的最大相似度都极低,它在任何匹配器下
都配不上**。本脚本量的是:LightGlue 真正匹配上的那些点,它们的 max-sim 下界在哪 ——
低于那个下界的点才是可以安全删的。

⚠️ 这是**在本数据上无损**,不是数学上无损。阈值必须留足余量,且最终以重建层验收。
"""
import argparse, json, sqlite3, sys
import numpy as np, torch
sys.path.insert(0, "/workspace/lgspike")
import lg_load, devutil

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="b28_src.db")
    ap.add_argument("--images", default="frames")
    ap.add_argument("--frame-map", default="b28_frame_map.json")
    ap.add_argument("--max-kpts", type=int, default=16384)
    ap.add_argument("--pairs", type=int, default=25)
    args = ap.parse_args()

    utils = lg_load.load("utils"); aliked = lg_load.load("aliked"); lg = lg_load.load("lightglue")
    dev = torch.device("cuda"); devutil.strict_fp32()

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    names = dict(db.execute("select image_id,name from images"))
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    db.close()
    step = max(1, len(pairs)//args.pairs); pairs = pairs[::step][:args.pairs]
    need = sorted({i for p in pairs for i in (p//MAX_IMAGE_ID, p%MAX_IMAGE_ID)})

    fmap = json.load(open(args.frame_map))
    ex = aliked.ALIKED(max_num_keypoints=args.max_kpts, detection_threshold=0.02).eval().to(dev)
    feats = {}
    for iid in need:
        img = utils.load_image(f"{args.images}/{fmap[str(iid)]}").to(dev)
        with torch.no_grad():
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                f = ex.extract(img, resize=1600)
        feats[iid] = {k: (v[0].float() if torch.is_floating_point(v) else v[0]) for k, v in f.items()}
        del img, f
    del ex; torch.cuda.empty_cache()

    m = lg.LightGlue(features="aliked", depth_confidence=0.95, width_confidence=0.99).eval().to(dev)

    lows, keeps = [], {t: [] for t in (0.2,0.3,0.4,0.5,0.6)}
    for pid in pairs:
        i1, i2 = pid//MAX_IMAGE_ID, pid%MAX_IMAGE_ID
        if i1 not in feats or i2 not in feats: continue
        d0, d1 = feats[i1]["descriptors"], feats[i2]["descriptors"]
        with torch.no_grad():
            sim = d0 @ d1.T                       # 已 L2 归一化 ⇒ 余弦
            ms0 = sim.max(dim=1).values           # 图1每点对图2的最大相似度
            pred = m({"image0": {k: v[None] for k, v in feats[i1].items()},
                      "image1": {k: v[None] for k, v in feats[i2].items()}})
        mt = pred["matches"][0]
        if len(mt) == 0: continue
        matched_ms = ms0[mt[:, 0]]
        lows.append(matched_ms.min().item())
        for t in keeps: keeps[t].append((ms0 >= t).float().mean().item())
        del sim, ms0

    print(f"{len(lows)} 对,起始 {args.max_kpts} 点/图\n")
    print(f"被 LightGlue 匹配上的点,其 max-sim 的最小值:")
    print(f"  跨对最小 {min(lows):.4f}   中位 {np.median(lows):.4f}   p10 {np.percentile(lows,10):.4f}")
    print(f"\n{'阈值':>6} {'保留点':>8} {'N² 省':>8} {'是否安全(< 跨对最小)':>22}")
    for t in sorted(keeps):
        f = float(np.mean(keeps[t]))
        safe = "✅ 安全" if t < min(lows) else "❌ 会杀真匹配"
        print(f"{t:>6.1f} {f*100:>7.1f}% {1/max(f,1e-9)**2:>7.2f}× {safe:>22}")


if __name__ == "__main__":
    main()
