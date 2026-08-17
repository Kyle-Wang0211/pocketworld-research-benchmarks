#!/usr/bin/env python3
"""在 97 帧真机 fixture 上跑 CasDiffMVS,建立**提速前的基线**。

  python3.11 bench_fixture97.py --fixture .../fixture97 --ckpt X.ckpt --tag C --out .../bench

产出三样东西,每样都有明确用途:

  1. depth/*.npy + conf/*.npy  ← **无损提速的唯一裁判**
     以后任何提速改动都跟这批深度图**逐像素**比,而不是跟稀疏点指标比。
     理由见 3:稀疏点指标对无纹理区是结构性盲区(08-17 已被肉眼推翻过一次)。

  2. 逐模块耗时拆解 ← 提速要打哪儿,由它决定,不由直觉决定
     用 forward hook + 显式 synchronize 量。MPS 是异步的,不 sync 量到的是提交时间不是执行时间。

  3. <1% / <5% 稀疏点指标 ← 只作**绝对锚点**,不作判决依据
     ⚠️ 三个已知失真,都不修,但都必须报出来:
        a) 可见性是**投影近似**,不考虑遮挡 ⇒ 被遮挡的点会贡献假误差,指标被系统性压低。
           但同一批点对所有权重一视同仁 ⇒ **相对比较有效,绝对值不可跨数据集比**。
        b) SfM 点只长在有纹理处。白墙/地板一个点都没有 ⇒ 指标看不见那里的质量。
        c) 稀疏点自身有重投影误差(本次 1.2213 px),不是真值,是"另一个估计"。

⚠️ fixture 的 K 是各向异性(fx=635.4 / fy=484.1):原图 4:3 被拉伸进 16:9。
   K 缩放自洽所以数学没错,但这是训练分布里没有的形变。单独立项量,不在本脚本里改。
"""
import argparse, json, os, sys, time
from types import SimpleNamespace
import numpy as np
import torch

ND = 384
# 🔴 NIMG 必须从 fixture 的 num_src 推出来,不能写死。
#    踩过:写死 5 时,num_view 5→7 那一臂**静默无效** —— 耗时与基线相同(228 vs 226ms)
#    才露馅。若不是速度对不上,会得出"num_view 无影响"的假结论。
# W/H 一律从 frames.json 读,不写死 —— 踩过:fixture 从 896×512 改成 768×576 后
# 这里还是旧常量,reshape 会静默错位(元素总数刚好对不上才炸,对得上就出假结果)。


def build_model(ckpt, dev):
    a = SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=ND,
        scale=[0.0, 0.125, 0.025], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000], stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4],
        CostNum=[0, 4, 4], hidden_dim=[0, 32, 20], context_dim=[32, 32, 16],
        unet_dim=[0, 16, 8], min_radius=0.125, max_radius=8)
    from models import CasDiffMVS
    m = CasDiffMVS(a, test=True)
    st = torch.load(ckpt, map_location="cpu")
    sd = st.get("model", st)
    r = m.load_state_dict(sd, strict=False)
    miss = [k for k in getattr(r, "missing_keys", []) if "num_batches" not in k]
    if miss:
        sys.exit(f"🔴 权重缺 {len(miss)} 个 key,前 5: {miss[:5]} —— 停,别跑出个假基线")
    return m.eval().to(dev)


class CachedFeature(torch.nn.Module):
    """特征缓存:同一张图的特征只算一次。

    为什么这是**真无损**而不是近似:eval 模式下 FeatureNet 无 dropout、BN 走 running stats,
    对同一输入是纯函数 ⇒ 缓存命中返回的张量与重算的**逐比特相同**。省的是纯冗余。

    冗余从哪来:97 帧 × 5 视图 = 485 次调用,但只有 97 张不同的图 —— 每张图当 1 次
    参考帧 + 约 4 次源帧,被重算 5 遍。

    ⚠️ 端上不能像这里一样缓存全部 97 帧(见 --feat-window)。生产里邻居都在附近帧,
       一个小窗口的 LRU 就够;这里默认不设上限是为了量**收益上界**。
    """
    def __init__(self, inner, window=0):
        super().__init__()
        self.inner, self.window = inner, window
        self.cache, self.order, self.keys = {}, [], []
        self.hit = self.miss = 0

    def forward(self, x):
        k = self.keys.pop(0)
        if k in self.cache:
            self.hit += 1
            self.order.remove(k); self.order.append(k)
            return self.cache[k]
        self.miss += 1
        f = self.inner(x)
        self.cache[k] = f; self.order.append(k)
        if self.window and len(self.order) > self.window:
            del self.cache[self.order.pop(0)]
        return f

    def bytes(self):
        return sum(t.numel() * t.element_size()
                   for f in self.cache.values() for t in f.values())


def attach_timers(model, dev):
    """逐模块耗时。MPS/CUDA 都是异步的,必须 sync 才量到执行时间。"""
    acc, t0 = {}, {}
    sync = (lambda: torch.mps.synchronize()) if dev.type == "mps" else \
           (lambda: torch.cuda.synchronize()) if dev.type == "cuda" else (lambda: None)

    def pre(name):
        def f(*_):
            sync(); t0[name] = time.perf_counter()
        return f

    def post(name):
        def f(*_):
            sync(); acc[name] = acc.get(name, 0.0) + time.perf_counter() - t0[name]
        return f

    for n, c in model.named_children():
        if sum(p.numel() for p in c.parameters()) == 0 and n != "GetCost":
            continue
        c.register_forward_pre_hook(pre(n))
        c.register_forward_hook(post(n))
    return acc, sync


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=os.path.expanduser(
        "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs"))
    ap.add_argument("--device", default="auto")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=-1,
                    help="每帧前重置 RNG。🔴 不设种子时本模型**推理不可复现**:"
                         "update.py:479 的扩散起始噪声是随机的(官方设计),"
                         "同权重同输入两跑 21.5%% 的像素差 >1%%。"
                         "要做逐比特对拍就必须设种子,否则对拍的是噪声。")
    ap.add_argument("--cache-feat", action="store_true", help="开特征缓存(逐比特无损)")
    ap.add_argument("--fuse-conv3d", action="store_true",
                    help="把划算的 3D 卷积换成等价单次 2D 卷积(权重重排,不重训)。"
                         "数值等价非逐比特(~1e-6,fp32 舍入量级)。")
    ap.add_argument("--fuse-all", action="store_true", help="强制全改(含实测变慢的层),仅供对照")
    ap.add_argument("--feat-window", type=int, default=0, help="LRU 窗口,0=不限(收益上界)")
    args = ap.parse_args()
    sys.path.insert(0, args.repo)

    dev = torch.device(
        args.device if args.device != "auto" else
        ("cuda" if torch.cuda.is_available() else
         "mps" if torch.backends.mps.is_available() else "cpu"))

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    NIMG = meta["num_src"] + 1
    assert W % 32 == 0 and H % 32 == 0, f"{W}×{H} 不是 32 的倍数,四级金字塔会错位"
    print(f"fixture {W}×{H} ×{NF} 帧  宽高比 {W/H:.4f}  num_view={NIMG}")
    IM = np.fromfile(f"{FX}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    nrun = args.limit or NF

    model = build_model(args.ckpt, dev)
    if args.fuse_conv3d or args.fuse_all:
        from models.conv3d_as_2d import convert_
        model = model.cpu()                      # 权重重排在 CPU 上做,避免 MPS 上的拷贝语义坑
        n = convert_(model, (lambda m: True) if args.fuse_all else None) \
            if args.fuse_all else convert_(model)
        model = model.to(dev)
        print(f"3D→2D 融合:替换 {n} 个卷积{'(强制全改)' if args.fuse_all else '(逐层取优)'}")
    feat_cache = None
    if args.cache_feat:
        feat_cache = CachedFeature(model.feature, args.feat_window)
        model.feature = feat_cache
        print(f"特征缓存 开  窗口={args.feat_window or '不限'}")
    acc, sync = attach_timers(model, dev)

    od = f"{args.out}/{args.tag}"
    os.makedirs(f"{od}/depth", exist_ok=True)
    os.makedirs(f"{od}/conf", exist_ok=True)

    per_frame = []
    for f in range(nrun):
        view = [f] + list(NB[f][:NIMG - 1])
        imgs = [torch.from_numpy(np.repeat(IM[v].astype(np.float32)[None], 3, 0)[None]).to(dev)
                for v in view]
        Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
        wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3), CM[v, 18:21][:, None]]),
                                  [0, 0, 0, 1]]).astype(np.float32) for v in view])
        base = np.zeros((NIMG, 2, 4, 4), np.float32)
        base[:, 0] = wc
        base[:, 1, :3, :3] = Ks
        pm = {}
        for s, dv_ in (("stage1", 8.), ("stage2", 4.), ("stage3", 2.), ("stage4", 1.)):
            mm = base.copy()
            mm[:, 1, :2, :] = base[:, 1, :2, :] / dv_
            pm[s] = torch.from_numpy(mm[None]).to(dev)
        if args.seed >= 0:
            # 逐帧重置而非全局设一次:这样每帧的噪声只取决于帧号,
            # 与"前面跑了多少帧""缓存改没改调用次数"都无关 ⇒ 对拍才干净。
            torch.manual_seed(args.seed + f)
            if dev.type == "mps":
                torch.mps.manual_seed(args.seed + f)
        if feat_cache is not None:
            feat_cache.keys = [int(v) for v in view]   # forward 按 imgs 顺序逐个取
        dmin, dmax = float(CM[f, 24]), float(CM[f, 25])
        dvals = torch.from_numpy(
            np.linspace(1 / dmax, 1 / dmin, ND, dtype=np.float32)[None]).to(dev)

        sync(); t0 = time.perf_counter()
        with torch.no_grad():
            o = model(imgs, pm, dvals)
        sync(); dt = time.perf_counter() - t0
        if f > 0:                      # 第 0 帧是编译/预热,不计入
            per_frame.append(dt)
        d = o["depth"][-1][0].float().cpu().numpy()
        # 🔴 官方 filter.py 的光度门是**三阶段 AND**(photo_thres 0.3/0.5/0.5),
        #    只存末阶段会让光度门形同虚设 —— 这是我 08-17 的一个真实偏差。
        cs = o["photometric_confidence"]
        np.save(f"{od}/depth/{f:04d}.npy", d.astype(np.float32))
        for k, cc in enumerate(cs):
            os.makedirs(f"{od}/conf{k}", exist_ok=True)
            np.save(f"{od}/conf{k}/{f:04d}.npy",
                    cc[0].float().cpu().numpy().astype(np.float32))
        c = cs[-1][0].float().cpu().numpy()
        np.save(f"{od}/conf/{f:04d}.npy", c.astype(np.float32))
        if f == 1:
            acc.clear()                # 预热后重置模块计时
        if f % 20 == 0:
            print(f"  帧{f:3d}/{nrun}  {dt*1000:6.1f} ms  深度形状{d.shape} p50={np.median(d):.2f}m",
                  flush=True)

    n = max(1, nrun - 1)
    ms = 1000 * float(np.mean(per_frame))
    print(f"\n══ {args.tag} @ {dev.type} ══")
    print(f"稳态 {ms:.1f} ms/帧 (p50 {1000*np.median(per_frame):.1f}, "
          f"min {1000*min(per_frame):.1f}, max {1000*max(per_frame):.1f}) "
          f"⇒ {nrun} 帧 {ms*nrun/1000:.1f}s")
    print("\n逐模块耗时(占单帧总时长):")
    tot = sum(acc.values())
    for k, v in sorted(acc.items(), key=lambda x: -x[1]):
        print(f"  {k:26s} {1000*v/n:7.2f} ms  {100*v/tot:5.1f}% of 模块合计")
    print(f"  {'—— 模块合计':26s} {1000*tot/n:7.2f} ms  "
          f"({100*tot/(n*ms/1000):.1f}% of 单帧;差额=模块外的 warp/采样/调度)")

    if feat_cache is not None:
        n_call = feat_cache.hit + feat_cache.miss
        print(f"\n特征缓存:命中 {feat_cache.hit}/{n_call} ({100*feat_cache.hit/n_call:.1f}%)"
              f"  缓存驻留 {feat_cache.bytes()/1e6:.0f} MB ({len(feat_cache.cache)} 帧)")

    json.dump({"tag": args.tag, "device": dev.type, "frames": nrun,
               "ms_per_frame": ms, "ms_p50": 1000 * float(np.median(per_frame)),
               "modules_ms": {k: 1000 * v / n for k, v in acc.items()},
               "ckpt": os.path.abspath(args.ckpt)},
              open(f"{od}/timing.json", "w"), indent=2)
    print(f"\n深度/置信度 → {od}/  (提速后跟这批逐像素比)")


if __name__ == "__main__":
    main()
