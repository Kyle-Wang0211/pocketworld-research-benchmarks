#!/usr/bin/env python3
"""跑一条臂的 CasDiffMVS 推理 —— 官方加载器 + 官方保存格式,唯一增量是**固定噪声**。

  python3.11 run_arm.py --mvs_in .../mvs_P16k --out .../out_P16k --ckpt .../C.ckpt

🔴 为什么要自己写而不直接用 test.py:
   handoff 的第一优先级是"必须先测噪声地板"。方案 A(首选)是把扩散噪声做成
   **外部输入并在各臂间固定** —— 官方 test.py 没有这个入口。
   本文件**逐字照抄** test.py 的模型构造、推理调用、保存格式(pfm/cam/conf0-2),
   只把 `model(...)` 多传一个 ext_noise。传 None 时行为与官方逐字相同。

   实测依据(2026-08-17):外部注入的噪声与模型内部 randn_like **97 帧逐比特相同**。
   不固定噪声的话,同输入两跑 21.5% 的像素深度差 >1%,任何臂间差异都不可解释。

⚠️ 噪声按**帧号**确定(seed = base + frame_index),与臂无关
   ⇒ 三条臂的同一帧吃到完全相同的噪声张量。
⚠️ 分辨率 768×576、num_view 10、ckpt 用我们自训的 C 权重(零 DTU)——
   handoff 写的 casdiffmvs_blendmvg 带 DTU 血统(官方 README 逐字:
   "Instead of finetuning DTU-pretrained model on BlendedMVS, we finetune it on BlendedMVG"),
   不能出货,拿它测对生产没有意义。
"""
import argparse, os, sys, time
from types import SimpleNamespace
import numpy as np
import torch
import cv2

# ⚠️ 硬编码 Mac 路径会让脚本在别的机器上直接 ModuleNotFoundError
# (2026-08-19 在租的机器上踩到)。允许用 DIFFMVS_REPO 覆盖。
REPO = os.environ.get("DIFFMVS_REPO") or os.path.expanduser(
    "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, REPO)
from datasets import find_dataset_def                      # noqa: E402
from models import CasDiffMVS                              # noqa: E402
from datasets.data_io import save_pfm, write_cam           # noqa: E402
from utils import tocuda, tensor2numpy                     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mvs_in", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--num_view", type=int, default=10)
    ap.add_argument("--max_w", type=int, default=768)
    ap.add_argument("--max_h", type=int, default=576)
    ap.add_argument("--noise_seed", type=int, default=20260818)
    ap.add_argument("--no_fixed_noise", action="store_true",
                    help="退回官方随机行为(仅用于测方案 B 的噪声地板)")
    args = ap.parse_args()

    # 官方真实场景档(ETH3D/T&T),逐字
    a = SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=384,
        scale=[0.0, 0.125, 0.025], sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000], stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4],
        CostNum=[0, 4, 4], hidden_dim=[0, 32, 20], context_dim=[32, 32, 16],
        unet_dim=[0, 16, 8], min_radius=0.125, max_radius=8)

    MVSDataset = find_dataset_def("mvs")
    # ⚠️ 签名是 n_views/numdepth,没有 mode/nviews/ndepths(照抄前先看源码)。
    #    dataset="general" 这一档才用 cams/ 目录且不带 scan 子目录 —— 正是
    #    colmap_input.py 的产物布局。
    ds = MVSDataset(args.mvs_in, n_views=args.num_view, numdepth=384,
                    dataset="general", scan=None,
                    max_w=args.max_w, max_h=args.max_h)
    loader = torch.utils.data.DataLoader(ds, 1, shuffle=False, num_workers=2,
                                         drop_last=False)
    print(f"数据集 {len(ds)} 帧  {args.max_w}x{args.max_h}  num_view={args.num_view}")

    model = CasDiffMVS(a, test=True)
    st = torch.load(args.ckpt, map_location="cpu")
    r = model.load_state_dict(st.get("model", st), strict=False)
    miss = [k for k in getattr(r, "missing_keys", []) if "num_batches" not in k]
    if miss:
        sys.exit(f"🔴 权重缺 {len(miss)} 个 key —— 停")
    dev = "cuda" if torch.cuda.is_available() else \
          ("mps" if torch.backends.mps.is_available() else "cpu")
    model.to(dev).eval()
    print(f"设备 {dev}  权重 {os.path.basename(args.ckpt)}"
          f"  噪声 {'固定 seed=%d' % args.noise_seed if not args.no_fixed_noise else '官方随机'}")

    ts = []
    with torch.no_grad():
        for bi, sample in enumerate(loader):
            depth_max = 1. / sample["depth_values"][:, 0]
            depth_min = 1. / sample["depth_values"][:, -1]
            # 🔴 sample 里三种容器都有:张量、dict(proj_matrices 分 stage)、
            #    **list(imgs 是逐视图的张量列表)**。我第一版漏了 list 那一支,
            #    图像留在 CPU 而权重在 MPS ⇒ slow_conv2d_forward_mps 设备不匹配。
            def _to(x):
                if torch.is_tensor(x): return x.to(dev)
                if isinstance(x, dict): return {k: _to(v) for k, v in x.items()}
                if isinstance(x, (list, tuple)): return type(x)(_to(v) for v in x)
                return x
            sc = tocuda(sample) if dev == "cuda" else _to(sample)
            depth_max = tensor2numpy(depth_max); depth_min = tensor2numpy(depth_min)

            ext = None
            if not args.no_fixed_noise:
                # 噪声只依赖帧号 ⇒ 各臂同帧吃到完全相同的张量
                g = torch.Generator(device="cpu").manual_seed(args.noise_seed + bi)
                H, W = args.max_h, args.max_w
                ext = [torch.randn(1, 1, H // 4, W // 4, generator=g).to(dev),
                       torch.randn(1, 1, H // 2, W // 2, generator=g).to(dev)]

            if dev == "cuda":
                torch.cuda.synchronize()
            t0 = time.time()
            outputs = model(sc["imgs"], sc["proj_matrices"], sc["depth_values"],
                            ext_noise=ext)
            if dev == "cuda":
                torch.cuda.synchronize()
            ts.append(time.time() - t0)

            outputs = tensor2numpy(outputs)
            filenames = sample["filename"]
            cams = sample["proj_matrices"]["stage4"].numpy()
            imgs = sample["imgs"][0].numpy()
            confs = outputs["photometric_confidence"]
            # ↓↓↓ 以下保存逻辑逐字照抄 test.py 的 casdiffmvs 分支
            for filename, cam, img, depth_est, dmx, dmn in zip(
                    filenames, cams, imgs, outputs["depth"][-1], depth_max, depth_min):
                cam = cam[0]
                for sub, ext_ in (("depth_est", ".pfm"), ("cams", "_cam.txt"),
                                  ("images", ".jpg")):
                    os.makedirs(os.path.join(args.out, filename.format(sub, ext_))
                                .rsplit("/", 1)[0], exist_ok=True)
                save_pfm(os.path.join(args.out, filename.format("depth_est", ".pfm")), depth_est)
                write_cam(os.path.join(args.out, filename.format("cams", "_cam.txt")),
                          cam, dmx, dmn)
                im = np.clip(np.transpose(img, (1, 2, 0)) * 255, 0, 255).astype(np.uint8)
                cv2.imwrite(os.path.join(args.out, filename.format("images", ".jpg")),
                            cv2.cvtColor(im, cv2.COLOR_RGB2BGR))
            for i in range(3):
                cf = os.path.join(args.out, filenames[0].format("conf%d" % i, ".pfm"))
                os.makedirs(cf.rsplit("/", 1)[0], exist_ok=True)
                save_pfm(cf, confs[i].squeeze(0))
            if bi % 20 == 0:
                print(f"  {bi}/{len(ds)}  {1000*ts[-1]:.0f} ms", flush=True)

    w = ts[1:] or ts
    print(f"\n══ {os.path.basename(args.out)} ══")
    print(f"  推理 中位 {1000*np.median(w):.1f} ms/帧  合计 {sum(ts):.1f}s  ({len(ts)} 帧,已丢首帧)")


if __name__ == "__main__":
    main()
