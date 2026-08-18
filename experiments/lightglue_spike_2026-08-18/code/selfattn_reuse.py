#!/usr/bin/env python3
"""自注意力在不同配对间到底有多接近 —— 决定能缓存几层。

动机:LightGlue 每层 = 2 次自注意力(图内)+ 1 次交叉注意力。极线带只能治交叉那 1/3,
自注意力占 2/3 且**同一帧在 k 个配对里被重复算 k 次**。
第 0 层的自注意力输入只是"编码后的描述子",与配对无关 ⇒ 逐位相同,必然可缓存。
更深的层因为混入了交叉注意力才发散。问题是:发散得多快?

做法:固定一帧 A,取它参与的多个配对 (A,B1)...(A,Bm),抓每层自注意力**输出**中
属于 A 的那部分,两两比余弦。若第 L 层仍 >0.999,说明缓存到 L 层是近乎无损的。

⚠️ 这不是理论推导,是拿真实描述子跑真实权重量出来的。缓存几层的判据必须是
   重建层复验,这里只是先看有没有值得做的空间。
"""
import argparse, json, sqlite3, sys
import numpy as np
import torch

sys.path.insert(0, "/workspace/lgspike")
import lg_load, devutil

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="b28_src.db")
    ap.add_argument("--images", default="frames")
    ap.add_argument("--frame-map", default="b28_frame_map.json")
    ap.add_argument("--max-kpts", type=int, default=8192)
    ap.add_argument("--partners", type=int, default=6, help="同一帧取几个配对伙伴")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    utils = lg_load.load("utils")
    aliked = lg_load.load("aliked")
    lg = lg_load.load("lightglue")
    dev = torch.device(args.device); devutil.strict_fp32()

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    names = dict(db.execute("select image_id,name from images"))
    pairs = [p for (p,) in db.execute("select pair_id from matches order by rows desc")]
    db.close()

    # 挑一个参与配对最多的帧 A,以及它的若干伙伴
    from collections import Counter
    cnt = Counter()
    for p in pairs:
        cnt[p // MAX_IMAGE_ID] += 1; cnt[p % MAX_IMAGE_ID] += 1
    A = cnt.most_common(1)[0][0]
    partners = []
    for p in pairs:
        i1, i2 = p // MAX_IMAGE_ID, p % MAX_IMAGE_ID
        if i1 == A and i2 not in partners: partners.append(i2)
        elif i2 == A and i1 not in partners: partners.append(i1)
        if len(partners) >= args.partners: break
    print(f"锚帧 image_id={A}(参与 {cnt[A]} 对),伙伴 {partners}")

    fmap = json.load(open(args.frame_map))
    ex = aliked.ALIKED(max_num_keypoints=args.max_kpts, detection_threshold=0.02).eval().to(dev)
    feats = {}
    for iid in [A] + partners:
        img = utils.load_image(f"{args.images}/{fmap[str(iid)]}").to(dev)
        with torch.no_grad():
            f = ex.extract(img, resize=1600)
        feats[iid] = {k: v[0] for k, v in f.items()}
        del img, f
    del ex; torch.cuda.empty_cache()

    matcher = lg.LightGlue(features="aliked", depth_confidence=-1,
                           width_confidence=-1).eval().to(dev)
    n_layers = matcher.conf.n_layers

    # 钩住每层 transformer 的输出,取 desc0(锚帧 A 在 image0 位置)
    caught = {}
    hooks = []
    def mk(i):
        def hook(mod, inp, out):
            caught[i] = out[0].detach()[0]     # desc0: [N, D]
        return hook
    for i, tr in enumerate(matcher.transformers):
        hooks.append(tr.register_forward_hook(mk(i)))

    per_layer = {i: [] for i in range(n_layers)}
    ref = None
    for b in partners:
        d = {"image0": {k: v[None] for k, v in feats[A].items()},
             "image1": {k: v[None] for k, v in feats[b].items()}}
        caught.clear()
        with torch.no_grad():
            matcher(d)
        snap = {i: caught[i].clone() for i in caught}
        if ref is None:
            ref = snap
            continue
        for i in snap:
            a, c = ref[i].float(), snap[i].float()
            cos = torch.nn.functional.cosine_similarity(a, c, dim=-1)
            per_layer[i].append((cos.mean().item(), cos.min().item()))
    for h in hooks: h.remove()

    print(f"\n锚帧 A 的自注意力输出,在 {len(partners)} 个不同配对之间的相似度:")
    print(f"{'层':>3} {'余弦均值':>10} {'余弦最小':>10}  {'可缓存?':>8}")
    for i in range(n_layers):
        if not per_layer[i]: continue
        m = np.mean([x[0] for x in per_layer[i]])
        lo = np.min([x[1] for x in per_layer[i]])
        tag = "✅" if m > 0.999 else ("⚠️" if m > 0.99 else "❌")
        print(f"{i:>3} {m:>10.6f} {lo:>10.6f}  {tag:>8}")


if __name__ == "__main__":
    main()
