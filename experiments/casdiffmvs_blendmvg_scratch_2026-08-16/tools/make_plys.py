#!/usr/bin/env python3
"""为每个权重产出真彩 PLY —— 用**官方 filter.py 融合**,四个权重完全同参。

⚠️ 为什么走官方融合而不是自己写:standing rule「能复刻就不自研」,
   而且自研融合会引入第二变量,肉眼对比就分不清是权重差异还是融合差异。

融合参数取自官方 scripts/test/test_eth_casdiffmvs.sh(真实场景档):
   photo_thres 0.3 0.5 0.5,geo 用 filter_depth 默认(mask>=3 / 1.0px / 0.01)

用法:
   python make_plys.py <fixture目录> <rgb目录> <输出根> <tag=ckpt> [<tag=ckpt> ...]
"""
from __future__ import annotations
import os, sys, shutil, json
from types import SimpleNamespace
import numpy as np
import torch

sys.path.insert(0, "/workspace/diffmvs")
from models import CasDiffMVS                                   # noqa: E402
from datasets.data_io import save_pfm, write_cam                # noqa: E402
from filter import filter_depth                                 # noqa: E402

W, H, NIMG, NDEPTH = 896, 512, 5, 384


def cas_args():
    return SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=NDEPTH,
        scale=[0.0, 0.125, 0.025],                # 官方真实场景档
        sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000],
        stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4], CostNum=[0, 4, 4],
        hidden_dim=[0, 32, 20], context_dim=[32, 32, 16], unet_dim=[0, 16, 8],
        min_radius=0.125, max_radius=8,
    )


def build_static(fx, rgb, out, CM, NB, NF):
    """cams/ images/ pair.txt —— 四个权重共用,只建一次。"""
    os.makedirs(f"{out}/cams", exist_ok=True)
    os.makedirs(f"{out}/images", exist_ok=True)
    for f in range(NF):
        K = CM[f, 0:9].reshape(3, 3)
        e = np.eye(4, dtype=np.float32)
        e[:3, :3] = CM[f, 9:18].reshape(3, 3); e[:3, 3] = CM[f, 18:21]
        # ⚠️ write_cam 末行是 "depth_max depth_min"(read_camera_parameters
        #    读 [0]=max [1]=min),顺序写反会静默出错
        write_cam(f"{out}/cams/{f:0>8}_cam.txt", [e, K],
                  float(CM[f, 25]), float(CM[f, 24]))
        shutil.copyfile(f"{rgb}/{f:0>8}.jpg", f"{out}/images/{f:0>8}.jpg")
    with open(f"{out}/pair.txt", "w") as fh:
        fh.write(f"{NF}\n")
        for f in range(NF):
            src = [int(x) for x in NB[f] if 0 <= int(x) < NF]
            fh.write(f"{f}\n{len(src)} " + " ".join(f"{s} 100" for s in src) + "\n")


def main() -> int:
    fx, rgb, root = sys.argv[1], sys.argv[2], sys.argv[3]
    jobs = [a.split("=", 1) for a in sys.argv[4:]]
    dev = torch.device("cuda")

    meta = json.load(open(f"{fx}/frames.json")); NF = meta["count"]
    IM = np.fromfile(f"{fx}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{fx}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{fx}/neighbors.i32", np.int32).reshape(NF, 4)
    args = cas_args()

    for tag, cp in jobs:
        out = f"{root}/{tag}"
        os.makedirs(out, exist_ok=True)
        print(f"\n════ {tag} ← {os.path.basename(cp)} ════", flush=True)
        build_static(fx, rgb, out, CM, NB, NF)

        model = CasDiffMVS(args, test=True)
        st = torch.load(cp, map_location="cpu")
        sd = st["model"] if "model" in st else st
        r = model.load_state_dict(sd, strict=False)
        if getattr(r, "missing_keys", None):
            print(f"🔴 缺 {len(r.missing_keys)} 个 key,跳过"); continue
        model.eval().to(dev)

        for d in ("depth_est", "conf0", "conf1", "conf2"):
            os.makedirs(f"{out}/{d}", exist_ok=True)
        for f in range(NF):
            view = [f] + [int(x) for x in NB[f]]
            imgs = [torch.from_numpy(np.repeat(IM[v].astype(np.float32)[None], 3, 0)[None]).to(dev)
                    for v in view]
            Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
            wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3),
                                                 CM[v, 18:21][:, None]]),
                                      [0, 0, 0, 1]]).astype(np.float32) for v in view])
            base = np.zeros((NIMG, 2, 4, 4), np.float32)
            base[:, 0] = wc; base[:, 1, :3, :3] = Ks
            pm = {}
            for s, dv_ in (("stage1", 8.0), ("stage2", 4.0), ("stage3", 2.0), ("stage4", 1.0)):
                m = base.copy(); m[:, 1, :2, :] = base[:, 1, :2, :] / dv_
                pm[s] = torch.from_numpy(m[None]).to(dev)
            dmin, dmax = float(CM[f, 24]), float(CM[f, 25])
            dv = torch.from_numpy(np.linspace(1.0/dmax, 1.0/dmin, NDEPTH, dtype=np.float32)[None]).to(dev)
            with torch.no_grad():
                o = model(imgs, pm, dv)
            save_pfm(f"{out}/depth_est/{f:0>8}.pfm", o["depth"][-1][0].float().cpu().numpy())
            for i in range(3):
                save_pfm(f"{out}/conf{i}/{f:0>8}.pfm",
                         o["photometric_confidence"][i].squeeze(0).float().cpu().numpy())
            if f % 40 == 0: print(f"  推理 {f}/{NF}", flush=True)
        del model; torch.cuda.empty_cache()

        ply = f"{root}/{tag}.ply"
        print(f"  融合 → {ply}", flush=True)
        filter_depth(out, out, ply, photo_thres=[0.3, 0.5, 0.5],
                     method="casdiffmvs", dataset="general")
        print(f"  ✅ {ply}  {os.path.getsize(ply)/2**20:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
