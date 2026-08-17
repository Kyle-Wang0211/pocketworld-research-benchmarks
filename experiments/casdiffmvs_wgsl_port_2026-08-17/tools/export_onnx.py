#!/usr/bin/env python3
"""A1:把 CasDiffMVS 导出成 ONNX(为 ORT-WebGPU 跨端做准备)。

  python3.11 export_onnx.py --fixture .../fx_official --ckpt .../casdiffmvs_C_long_ep31.ckpt \
      --out .../casdiffmvs.onnx [--fuse-conv3d]

三个刻意的设计,每个都有理由:

  ① **噪声做成图的输入**,不让图里出现 `RandomNormalLike`。
     理由 a:交付要可复现(08-14 记载导出图里有 RandomNormalLike,直接撞"可复现"铁律);
     理由 b:逐 stage 对拍否则测的是噪声(同输入两跑 21.5% 像素差 >1%)。
     实测本配置每次前向**只有 2 个随机源**(stage2/stage3 各一个)——
     `sampling_timesteps=1` 让 `time_pairs` 只剩 (999,-1) 一对,`time_next<0` 直接
     continue,第二处 randn_like 走不到。

  ② **可选先做 3D→2D 卷积融合**(`--fuse-conv3d`)。11 个 3D 卷积里 7 个变成
     单次 Conv2d(权重重排不重训,数值等价 ~1e-6),**两个 ConvTranspose3d 都在其中**。
     ⇒ 导出图里少掉最容易出兼容问题的算子。

  ③ **扁平签名**:ONNX 不接受 list/dict 输入,包一层 wrapper。

⚠️ 本脚本只负责导出 + 与 PyTorch 对拍。ORT 侧的跑通在 A2/A3。
"""
import argparse, json, os, sys
from types import SimpleNamespace
import numpy as np
import torch

ND = 384


class Flat(torch.nn.Module):
    """把 (list, dict, ...) 的签名压平成 ONNX 能接受的张量列表。"""

    def __init__(self, core, nimg):
        super().__init__()
        self.core = core
        self.nimg = nimg

    def forward(self, imgs, pm1, pm2, pm3, pm4, depth_values, noise2, noise3):
        il = [imgs[:, i] for i in range(self.nimg)]
        pm = {"stage1": pm1, "stage2": pm2, "stage3": pm3, "stage4": pm4}
        o = self.core(il, pm, depth_values, ext_noise=[noise2, noise3])
        c = o["photometric_confidence"]
        return o["depth"][-1], c[0], c[1], c[2]


def build(ckpt, fuse, repo):
    sys.path.insert(0, repo)
    from models import CasDiffMVS
    a = SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=ND,
        scale=[0.0, 0.125, 0.025], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000], stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4],
        CostNum=[0, 4, 4], hidden_dim=[0, 32, 20], context_dim=[32, 32, 16],
        unet_dim=[0, 16, 8], min_radius=0.125, max_radius=8)
    m = CasDiffMVS(a, test=True)
    st = torch.load(ckpt, map_location="cpu")
    r = m.load_state_dict(st.get("model", st), strict=False)
    miss = [k for k in getattr(r, "missing_keys", []) if "num_batches" not in k]
    if miss:
        sys.exit(f"🔴 权重缺 {len(miss)} 个 key —— 停")
    if fuse:
        from models.conv3d_as_2d import convert_
        n = convert_(m)
        print(f"3D→2D 融合:替换 {n} 个卷积")
    return m.eval()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=os.path.expanduser(
        "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs"))
    ap.add_argument("--fuse-conv3d", action="store_true")
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--frame", type=int, default=5)
    args = ap.parse_args()

    meta = json.load(open(f"{args.fixture}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    NIMG = meta["num_src"] + 1
    IM = np.fromfile(f"{args.fixture}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{args.fixture}/cams.f32", np.float32).reshape(NF, 36)
    NBv = np.fromfile(f"{args.fixture}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    print(f"fixture {W}×{H}  num_view={NIMG}")

    model = build(args.ckpt, args.fuse_conv3d, args.repo)

    f = args.frame
    view = [f] + list(NBv[f])
    imgs = torch.from_numpy(
        np.stack([np.repeat(IM[v].astype(np.float32)[None], 3, 0) for v in view])[None])
    Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
    wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3), CM[v, 18:21][:, None]]),
                              [0, 0, 0, 1]]).astype(np.float32) for v in view])
    base = np.zeros((NIMG, 2, 4, 4), np.float32)
    base[:, 0] = wc
    base[:, 1, :3, :3] = Ks
    pms = []
    for dv_ in (8., 4., 2., 1.):
        mm = base.copy()
        mm[:, 1, :2, :] = base[:, 1, :2, :] / dv_
        pms.append(torch.from_numpy(mm[None]))
    dv = torch.from_numpy(np.linspace(1 / float(CM[f, 25]), 1 / float(CM[f, 24]),
                                      ND, dtype=np.float32)[None])
    g = torch.Generator().manual_seed(0)
    n2 = torch.randn(1, 1, H // 4, W // 4, generator=g)
    n3 = torch.randn(1, 1, H // 2, W // 2, generator=g)

    flat = Flat(model, NIMG).eval()
    with torch.no_grad():
        ref = flat(imgs, *pms, dv, n2, n3)
    print(f"PyTorch 参考:depth {tuple(ref[0].shape)}  conf {[tuple(c.shape) for c in ref[1:]]}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    names_in = ["imgs", "pm_stage1", "pm_stage2", "pm_stage3", "pm_stage4",
                "depth_values", "noise_stage2", "noise_stage3"]
    names_out = ["depth", "conf0", "conf1", "conf2"]
    try:
        torch.onnx.export(
            flat, (imgs, *pms, dv, n2, n3), args.out,
            input_names=names_in, output_names=names_out,
            opset_version=args.opset, do_constant_folding=True, dynamo=False)
    except Exception as e:
        print(f"\n🔴 导出失败:{type(e).__name__}\n{str(e)[:1500]}")
        return 1
    print(f"\n✅ 导出成功 → {args.out}  {os.path.getsize(args.out)/1e6:.1f} MB")

    # ── 算子清单:这是决定 ORT-WebGPU 能不能吃下的关键 ──
    import onnx
    g_ = onnx.load(args.out).graph
    from collections import Counter
    c = Counter(n.op_type for n in g_.node)
    print(f"\n算子种类 {len(c)},节点 {sum(c.values())}:")
    for k, v in c.most_common():
        print(f"  {k:28} {v}")
    rnd = [k for k in c if "Random" in k]
    print(f"\n{'🔴 图里仍有随机算子:' + str(rnd) if rnd else '✅ 图内无随机算子(噪声已是输入)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
