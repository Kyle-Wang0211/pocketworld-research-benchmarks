#!/usr/bin/env python3
"""depthnet 那 62ms 到底是算力还是 kernel 启动开销?

两个实验,各自能独立给出判据:

  ① **批量缩放**(决定性)
     喂 batch 1/2/4/8 的同一份输入。
       线性(4× 工作量 ≈ 4× 时间)  ⇒ 算力受限,只能靠减少工作量提速
       次线性(4× 工作量 ≪ 4× 时间)⇒ 启动/占用率受限,融合算子或换后端就能白捡

  ② **内部拆解**
     把 differentiable_warping / pixel_view_weight / cost_regularization / mask
     分别计时,看 62ms 花在哪一段。

⚠️ 量的是 PyTorch/MPS。CoreML 的调度完全不同(实测同模型 Mac 上 CoreML 127ms
   vs 这里 226ms)⇒ **比例可迁移,绝对值不可**。启动受限的结论如果成立,
   恰恰说明换到 CoreML 收益会更大。
"""
import argparse, json, os, sys, time
from types import SimpleNamespace
import numpy as np
import torch

ND_INIT = 48


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--repo", default=os.path.expanduser(
        "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs"))
    ap.add_argument("--iters", type=int, default=20)
    args = ap.parse_args()
    sys.path.insert(0, args.repo)
    import models.module as M
    from models import CasDiffMVS

    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    sync = (lambda: torch.mps.synchronize()) if dev.type == "mps" else (lambda: None)

    a = SimpleNamespace(method="casdiffmvs", numdepth_initial=ND_INIT, numdepth=384,
                        scale=[0.0, 0.125, 0.025], sampling_timesteps=[0, 1, 1],
                        ddim_eta=[0, 1, 1], timesteps=[1000] * 3, stage_iters=[1, 3, 3],
                        cost_dim_stage=[4, 4, 4], CostNum=[0, 4, 4], hidden_dim=[0, 32, 20],
                        context_dim=[32, 32, 16], unet_dim=[0, 16, 8],
                        min_radius=0.125, max_radius=8)
    model = CasDiffMVS(a, test=True)
    st = torch.load(args.ckpt, map_location="cpu")
    model.load_state_dict(st.get("model", st), strict=False)
    model.eval().to(dev)
    dn = model.depthnet

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    IM = np.fromfile(f"{FX}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])

    # ── 取第 5 帧的真实输入,先跑一遍主干拿到 depthnet 的实参 ──
    f = 5
    view = [f] + list(NB[f][:4])
    imgs = [torch.from_numpy(np.repeat(IM[v].astype(np.float32)[None], 3, 0)[None]).to(dev)
            for v in view]
    with torch.no_grad():
        feats = [model.feature(i) for i in imgs]
        ctx = model.context(imgs[0])
    fs = [ft["stage1"] for ft in feats]
    Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
    wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3), CM[v, 18:21][:, None]]),
                              [0, 0, 0, 1]]).astype(np.float32) for v in view])
    base = np.zeros((5, 2, 4, 4), np.float32)
    base[:, 0] = wc
    base[:, 1, :3, :3] = Ks
    base[:, 1, :2, :] /= 8.0
    pm = torch.from_numpy(base[None]).to(dev).float()

    B, C, h, w = fs[0].shape
    print(f"stage1 特征 {tuple(fs[0].shape)}  代价体 [{B},{C},{ND_INIT},{h},{w}] "
          f"= {C*ND_INIT*h*w/1e6:.2f} M 元素/视图  ×4 源视图")

    dmin, dmax = float(CM[f, 24]), float(CM[f, 25])
    from models.module import disp_to_depth
    from functools import partial
    siv = partial(disp_to_depth, min_depth=torch.tensor(dmin, device=dev),
                  max_depth=torch.tensor(dmax, device=dev))
    drs = torch.arange(0, ND_INIT, device=dev).view(1, -1, 1, 1) / (ND_INIT - 1.0)
    drs = drs.repeat(1, 1, h, w)
    drs = siv(drs)[1]
    context = torch.relu(ctx["stage1"])

    def run(nb):
        F_ = [x.repeat(nb, 1, 1, 1) for x in fs]
        c_ = context.repeat(nb, 1, 1, 1)
        p_ = pm.repeat(nb, 1, 1, 1, 1)
        d_ = drs.repeat(nb, 1, 1, 1)
        with torch.no_grad():
            for _ in range(3):
                dn(F_, c_, p_, depth_values=d_, scale_inv_depth=siv)
            sync(); t0 = time.perf_counter()
            for _ in range(args.iters):
                dn(F_, c_, p_, depth_values=d_, scale_inv_depth=siv)
            sync()
        return (time.perf_counter() - t0) / args.iters * 1000

    print("\n══ ① 批量缩放 ══")
    print(f"{'batch':>6} {'ms':>9} {'ms/样本':>9} {'相对 b1':>9}  判读")
    t1 = None
    for nb in (1, 2, 4, 8):
        try:
            t = run(nb)
        except RuntimeError as e:
            print(f"{nb:>6}  🔴 {str(e)[:60]}"); break
        t1 = t1 or t
        per, ratio = t / nb, t / t1
        verdict = ("启动受限" if ratio < nb * 0.7 else
                   "算力受限" if ratio > nb * 0.9 else "中间")
        print(f"{nb:>6} {t:9.2f} {per:9.2f} {ratio:8.2f}×  {verdict}")

    # ── ② 内部拆解 ──
    print("\n══ ② depthnet 内部拆解(batch 1)══")
    acc = {}
    orig_warp = M.differentiable_warping

    def timed_warp(*aa, **kk):
        sync(); t0 = time.perf_counter()
        r = orig_warp(*aa, **kk)
        sync(); acc["differentiable_warping"] = acc.get("differentiable_warping", 0) + \
            time.perf_counter() - t0
        return r
    M.differentiable_warping = timed_warp

    t0d = {}
    def pre(n):
        def g(*_):
            sync(); t0d[n] = time.perf_counter()
        return g
    def post(n):
        def g(*_):
            sync(); acc[n] = acc.get(n, 0) + time.perf_counter() - t0d[n]
        return g
    for n, c in dn.named_children():
        c.register_forward_pre_hook(pre(n)); c.register_forward_hook(post(n))

    with torch.no_grad():
        dn(fs, context, pm, depth_values=drs, scale_inv_depth=siv)   # 预热
        acc.clear()
        sync(); t0 = time.perf_counter()
        for _ in range(args.iters):
            dn(fs, context, pm, depth_values=drs, scale_inv_depth=siv)
        sync(); tot = (time.perf_counter() - t0) / args.iters * 1000
    M.differentiable_warping = orig_warp

    print(f"{'':28s} {'ms/帧':>8} {'%':>7}")
    for k, v in sorted(acc.items(), key=lambda x: -x[1]):
        ms = 1000 * v / args.iters
        print(f"  {k:26s} {ms:8.2f} {100*ms/tot:6.1f}%")
    named = sum(1000 * v / args.iters for v in acc.values())
    print(f"  {'—— 已归因':26s} {named:8.2f} {100*named/tot:6.1f}%")
    print(f"  {'—— 未归因(逐元素/reshape/调度)':26s} {tot-named:8.2f} {100*(tot-named)/tot:6.1f}%")
    print(f"  {'depthnet 合计':26s} {tot:8.2f}")


if __name__ == "__main__":
    main()
