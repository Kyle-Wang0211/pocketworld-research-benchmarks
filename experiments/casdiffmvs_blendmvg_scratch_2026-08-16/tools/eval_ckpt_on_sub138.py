#!/usr/bin/env python3
"""在 138 帧子集上跑 CasDiffMVS 推理并对稀疏点真值评测。

⚠️ 为什么不用现成的 dmcache_trio_*.npz 做基线:
   它们来自**另一个重建的 gauge**,与 trio_model_lapa 的稀疏点差一个约 1.10 的
   系统尺度(实测预测/真值比值 p50=1.1029)。拿它对 trio 真值算相对误差,
   <1% 只有 2%,量的是 gauge 不是精度 —— 是"换掉错尺子"那类陷阱。
   ⇒ 本脚本对**每个权重现跑推理**,两边走完全相同的路径,只有权重不同。

口径(两个权重完全一致):
   138 帧(413 帧 stride 3)/ 896×512 / 5 视图(ref + neighbors.i32 的 4 个)
   scale = [0, 0.125, 0.025](官方真实场景档,也是训练末段用的档)
   覆盖率 = 该帧观测点里预测深度>0 的比例
   <1%/<5% = 被覆盖的点里相对误差小于阈值的比例

用法:
   python eval_ckpt_on_sub138.py <fixture 目录> <trio npz> <ckpt> [<ckpt2> ...]
"""
from __future__ import annotations
import sys, time, json
from types import SimpleNamespace
import numpy as np
import torch

sys.path.insert(0, "/workspace/diffmvs")
from models import CasDiffMVS   # noqa: E402

W, H, NIMG, NDEPTH = 896, 512, 5, 384
STRIDE = 3


def cas_args():
    # 逐字取自 pw_diffmvs_common._args_casdiffmvs 的 PW_SCALE=real 档
    return SimpleNamespace(
        method="casdiffmvs", numdepth_initial=48, numdepth=NDEPTH,
        scale=[0.0, 0.125, 0.025],
        sampling_timesteps=[0, 1, 1], ddim_eta=[0, 1, 1],
        timesteps=[1000, 1000, 1000],
        stage_iters=[1, 3, 3], cost_dim_stage=[4, 4, 4], CostNum=[0, 4, 4],
        hidden_dim=[0, 32, 20], context_dim=[32, 32, 16], unet_dim=[0, 16, 8],
        min_radius=0.125, max_radius=8,
    )


def proj_ms(K, w2c, dev):
    """照 datasets/blend.py:112-160 构 4 个尺度的投影矩阵。"""
    n = len(K)
    base = np.zeros((n, 2, 4, 4), np.float32)
    for i in range(n):
        base[i, 0] = w2c[i]
        base[i, 1, :3, :3] = K[i]
    out = {}
    for s, div in (("stage1", 8.0), ("stage2", 4.0), ("stage3", 2.0), ("stage4", 1.0)):
        m = base.copy()
        m[:, 1, :2, :] = base[:, 1, :2, :] / div
        out[s] = torch.from_numpy(m[None]).to(dev)   # (1,n,2,4,4)
    return out


def main() -> int:
    fx, gtp = sys.argv[1], sys.argv[2]
    ckpts = sys.argv[3:]
    dev = torch.device("cuda")

    meta = json.load(open(f"{fx}/frames.json"))
    NF = meta["count"]
    IM = np.fromfile(f"{fx}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{fx}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{fx}/neighbors.i32", np.int32).reshape(NF, 4)

    g = np.load(gtp, allow_pickle=True)
    gK, gw2c, pts, oi, oo = g["K"], g["w2c"], g["pts"], g["obs_idx"], g["obs_off"]
    sel = list(range(0, len(g["names"]), STRIDE))[:NF]
    print(f"fixture {NF} 帧 | 真值帧索引 {sel[0]}..{sel[-1]}")

    args = cas_args()
    print(f"{'权重':<40}{'覆盖':>8}{'<1%':>8}{'<5%':>8}{'ms/帧':>9}")
    for cp in ckpts:
        model = CasDiffMVS(args, test=True)
        st = torch.load(cp, map_location="cpu")
        sd = st["model"] if "model" in st else st
        miss = model.load_state_dict(sd, strict=False)
        # 🔴 strict=False 会静默吞掉不匹配 —— 必须核对
        if getattr(miss, "missing_keys", None):
            print(f"🔴 {cp}: 缺 {len(miss.missing_keys)} 个 key,拒绝评测"); continue
        model.eval().to(dev)

        n_all = n_cov = n1 = n5 = 0; tsum = 0.0
        for f in range(NF):
            view = [f] + list(NB[f])
            imgs = [torch.from_numpy(
                np.repeat(IM[v].astype(np.float32)[None], 3, 0)[None]).to(dev) for v in view]
            K = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
            wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3),
                                                 CM[v, 18:21][:, None]]),
                                      [0, 0, 0, 1]]).astype(np.float32) for v in view])
            dmin, dmax = float(CM[f, 24]), float(CM[f, 25])
            dv = torch.from_numpy(np.linspace(1.0/dmax, 1.0/dmin, NDEPTH,
                                              dtype=np.float32)[None]).to(dev)
            torch.cuda.synchronize(); t0 = time.time()
            with torch.no_grad():
                out = model(imgs, proj_ms(K, wc, dev), dv)
            torch.cuda.synchronize(); tsum += time.time() - t0
            dep = out["depth"][-1][0].float().cpu().numpy()

            gi = sel[f]
            idx = oi[oo[gi]:oo[gi+1]]
            if len(idx) == 0: continue
            Xc = (gw2c[gi][:3, :3] @ pts[idx].T).T + gw2c[gi][:3, 3]
            zt = Xc[:, 2]; m = zt > 1e-6; Xc, zt = Xc[m], zt[m]
            uvw = (gK[gi] @ Xc.T).T
            u = np.round(uvw[:, 0]/uvw[:, 2]).astype(int)
            v = np.round(uvw[:, 1]/uvw[:, 2]).astype(int)
            inb = (u >= 0) & (u < W) & (v >= 0) & (v < H)
            u, v, zt = u[inb], v[inb], zt[inb]
            zp = dep[v, u]; cov = zp > 0
            rel = np.abs(zp[cov]-zt[cov])/zt[cov]
            n_all += len(zt); n_cov += int(cov.sum())
            n1 += int((rel < 0.01).sum()); n5 += int((rel < 0.05).sum())
        print(f"{cp.split('/')[-1]:<40}{100*n_cov/max(n_all,1):7.1f}%"
              f"{100*n1/max(n_cov,1):7.1f}%{100*n5/max(n_cov,1):7.1f}%{1000*tsum/NF:8.0f}")
        del model; torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
