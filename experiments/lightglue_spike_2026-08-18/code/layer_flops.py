#!/usr/bin/env python3
"""量 LightGlue 每层的**真实**点数与 FLOPs —— 我此前的账用的是估算的剪枝系数。

之前所有 A16 预算都建立在"剪枝均匀省 25%、平均停在 6.7/9 层"这个**估算**上,
从没量过宽度剪枝逐层把点砍到多少。若真实曲线比估算陡,分母全错、账要重算。

每层的注意力 FLOPs ≈ 4·N²·D(自注意力 ×2,交叉 ×1,各按当时的 N)。
"""
import argparse, json, sqlite3, sys
import numpy as np, torch
sys.path.insert(0, "/workspace/lgspike")
import lg_load, devutil

MAX_IMAGE_ID = 2147483647
D_MODEL = 256


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="b28_src.db")
    ap.add_argument("--images", default="frames")
    ap.add_argument("--frame-map", default="b28_frame_map.json")
    ap.add_argument("--max-kpts", type=int, default=16384)
    ap.add_argument("--pairs", type=int, default=30)
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
    n_layers = m.conf.n_layers

    seen = []          # 每对:每层进入时的 (n0, n1)
    def mk(i):
        def hook(mod, inp, out):
            d0 = inp[0]
            d1 = inp[1]
            cur.append((i, d0.shape[1], d1.shape[1]))
        return hook
    hooks = [tr.register_forward_pre_hook(
        lambda mod, inp, i=i: cur.append((i, inp[0].shape[1], inp[1].shape[1])))
        for i, tr in enumerate(m.transformers)]

    stops = []
    for pid in pairs:
        i1, i2 = pid//MAX_IMAGE_ID, pid%MAX_IMAGE_ID
        if i1 not in feats or i2 not in feats: continue
        d = {"image0": {k: v[None] for k, v in feats[i1].items()},
             "image1": {k: v[None] for k, v in feats[i2].items()}}
        cur = []
        with torch.no_grad(): pred = m(d)
        seen.append(cur); stops.append(int(pred["stop"]))
    for h in hooks: h.remove()

    N0 = args.max_kpts
    print(f"{len(seen)} 对,起始关键点 {N0},平均停在第 {np.mean(stops):.2f}/{n_layers} 层\n")
    print(f"{'层':>3} {'进入时 n0':>10} {'占初始':>8} {'该层 TFLOP':>12}")
    tot = 0.0
    for L in range(n_layers):
        ns = [(a, b) for c in seen for (i, a, b) in c if i == L]
        if not ns: continue
        n0 = np.mean([a for a, b in ns]); n1 = np.mean([b for a, b in ns])
        cover = len(ns) / len(seen)          # 有多少对跑到了这层
        f = (2*n0*n0 + 2*n1*n1 + 2*n0*n1) * D_MODEL * 2 / 1e12   # 自×2 + 交叉
        tot += f * cover
        print(f"{L:>3} {n0:>10.0f} {n0/N0*100:>7.1f}% {f*cover:>12.4f}")
    naive = (2*N0*N0*2 + 2*N0*N0) * D_MODEL * 2 / 1e12 * n_layers
    print(f"\n实测合计 {tot:.3f} TFLOP/对")
    print(f"不剪枝的朴素估算 {naive:.3f} TFLOP/对  ⇒ 剪枝真实省 {naive/tot:.2f}×")
    print(f"(我此前账里用的是 5.525 TFLOP/对)")


if __name__ == "__main__":
    main()
