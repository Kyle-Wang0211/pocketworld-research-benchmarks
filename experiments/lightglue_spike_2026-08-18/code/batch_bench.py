#!/usr/bin/env python3
"""批处理多对:同样的 FLOPs,更高的 GPU 利用率 —— 我一整天每次只喂一对。

官方自己在单张 24GB 卡上装 32 对的 batch。k=8 意味着每帧天然有 8 对可以一起做,
**不改算法、不改数值,纯粹是排布方式** ⇒ 完全无损。

我此前所有 A16 估算都假设 35% 利用率。若 batch 能把它推上去,那个假设要改,
整张账跟着改。

⚠️ 批处理要求同 batch 内关键点数一致(LightGlue 用 padding + mask)。
   我们每帧点数不同 ⇒ 用同一份特征复制成 batch 来量**纯粹的批处理增益**,
   不掺 padding 浪费;真实场景的增益会略低于此。
"""
import argparse, json, sqlite3, sys, time
import numpy as np, torch
sys.path.insert(0, "/workspace/lgspike")
import lg_load, devutil

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="frames")
    ap.add_argument("--frame-map", default="b28_frame_map.json")
    ap.add_argument("--db", default="b28_src.db")
    ap.add_argument("--max-kpts", type=int, default=16384)
    ap.add_argument("--batches", default="1,2,4,8")
    args = ap.parse_args()

    utils = lg_load.load("utils"); aliked = lg_load.load("aliked"); lg = lg_load.load("lightglue")
    dev = torch.device("cuda"); devutil.strict_fp32()
    fmap = json.load(open(args.frame_map))
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    ids = [i for (i,) in db.execute("select image_id from images order by image_id limit 2")]
    db.close()

    ex = aliked.ALIKED(max_num_keypoints=args.max_kpts, detection_threshold=0.02).eval().to(dev)
    fs = []
    for iid in ids:
        img = utils.load_image(f"{args.images}/{fmap[str(iid)]}").to(dev)
        with torch.no_grad():
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                f = ex.extract(img, resize=args.resize if hasattr(args,'resize') else 1600)
        fs.append({k: (v[0].float() if torch.is_floating_point(v) else v[0]) for k, v in f.items()})
        del img, f
    del ex; torch.cuda.empty_cache()
    n = fs[0]["keypoints"].shape[0]
    print(f"每图 {n} 关键点\n")

    m = lg.LightGlue(features="aliked", depth_confidence=0.95, width_confidence=0.99).eval().to(dev)
    print(f"{'batch':>6} {'总耗时ms':>10} {'每对ms':>9} {'相对 b=1':>10}")
    base = None
    for B in [int(x) for x in args.batches.split(",")]:
        d = {f"image{j}": {k: v[None].repeat(B, *([1]*v.dim()))
                           for k, v in fs[j].items()} for j in (0, 1)}
        try:
            for _ in range(2):
                with torch.no_grad(): m(d)
            torch.cuda.synchronize(); t0 = time.perf_counter()
            for _ in range(5):
                with torch.no_grad(): m(d)
            torch.cuda.synchronize()
            dt = (time.perf_counter()-t0)/5
        except torch.cuda.OutOfMemoryError:
            print(f"{B:>6}  OOM"); torch.cuda.empty_cache(); continue
        per = dt/B*1000
        if base is None: base = per
        print(f"{B:>6} {dt*1000:>10.1f} {per:>9.1f} {base/per:>9.2f}×")
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
