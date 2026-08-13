#!/usr/bin/env python3
"""决定性确认:把整图的 GroupNorm 统计量注入 tile,看误差是否塌到 ~0。

前一个实验(exp_tile_vs_whole.py)排除了两个嫌疑:
  - 不是 RNG(canonical noise 已接管,fallbacks=0,整图两遍逐位相同)
  - 不是源视图 ROI(模式 B 给全源图,interior 误差反而略增)
剩下的解释是网络里有跨空间全局耦合,而 update.py:121 的 `Block` 用的是
nn.GroupNorm(8, dim_out) —— PyTorch 的 GroupNorm 在 (C/G, H, W) 上求统计量,
**含全部空间位置**,所以 tile 一切就变。

本实验直接验证这个因果:
  record 模式:整图跑一遍,按调用顺序记下每个 GroupNorm 的 (mean,var)
  inject 模式:tile 跑时不算自己的统计量,改用整图记下来的那一份
若误差塌到 ~0 → 归因钉死,且同时证明"operator 级分块做全局两遍统计"确实能换回等价。
若不塌 → 还有别的全局耦合,这条路要重新评估。

⚠️ 必须先过的控制组:手写 GroupNorm(record 模式,用自己算的统计量)必须与官方
nn.GroupNorm 逐位相同。不过这一关的话,注入后的任何差异都归因不了。

用法: exp_tile_gn_inject.py [N_FRAMES] [DEVICE] [OUT_JSON]
"""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

RESEARCH = Path.home() / "Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python"
sys.path.insert(0, str(RESEARCH))

import pw_diffmvs_common as C      # noqa: E402
import pw_diffmvs_run as PR        # noqa: E402

H, W = PR.PROC_H, PR.PROC_W
N_VIEW = 5
CORE_H, CORE_W = H // 2, W // 2
HALOS = [0, 64, 192]
SEAM_BAND = 16

# ------------------------------------------------------------- canonical noise
_ORIG_RANDN_LIKE = torch.randn_like
_CTX = {"x0": 0, "y0": 0, "tw": W, "th": H, "draw": 0, "fields": {}, "fallbacks": 0}


def _field(draw: int, s: int) -> torch.Tensor:
    key = (draw, s)
    f = _CTX["fields"].get(key)
    if f is None:
        g = torch.Generator().manual_seed((draw * 1_000_003 + s * 7919) & 0x7FFFFFFF)
        f = torch.randn(H // s, W // s, generator=g)
        _CTX["fields"][key] = f
    return f


def _canonical_randn_like(t, *a, **k):
    shape = tuple(t.shape)
    h, w = shape[-2], shape[-1]
    th, tw = _CTX["th"], _CTX["tw"]
    draw = _CTX["draw"]; _CTX["draw"] += 1
    if h == 0 or w == 0 or th % h or tw % w or (th // h) != (tw // w):
        _CTX["fallbacks"] += 1
        return _ORIG_RANDN_LIKE(t, *a, **k)
    s = th // h
    sl = _field(draw, s)[_CTX["y0"] // s:_CTX["y0"] // s + h,
                         _CTX["x0"] // s:_CTX["x0"] // s + w]
    return sl.reshape((1,) * (len(shape) - 2) + (h, w)).expand(shape).to(
        device=t.device, dtype=t.dtype).contiguous()


# ------------------------------------------------------------- GroupNorm 接管
_GN = {"mode": "off", "idx": 0, "stats": {}, "misses": 0}
_ORIG_GN_FORWARD = nn.GroupNorm.forward


def _gn_forward(self, x):
    """手写 GroupNorm。mode:
       off    —— 用自己的统计量(应与官方逐位相同,这是控制组)
       record —— 用自己的统计量,并按调用序号记下来
       inject —— 用 record 阶段整图记下的统计量(形状 (B,G,1,1,1),与空间尺寸无关,
                 所以整图的统计量可以直接喂给任意大小的 tile)
    """
    i = _GN["idx"]; _GN["idx"] += 1
    B, Cc = x.shape[0], x.shape[1]
    G = self.num_groups
    xg = x.view(B, G, Cc // G, *x.shape[2:])
    dims = tuple(range(2, xg.dim()))
    if _GN["mode"] == "inject" and i in _GN["stats"]:
        mean, var = _GN["stats"][i]
        mean = mean.to(x.device, x.dtype); var = var.to(x.device, x.dtype)
    else:
        if _GN["mode"] == "inject":
            _GN["misses"] += 1        # 调用序号没对上 -> 结论要打折,必须报出来
        mean = xg.mean(dim=dims, keepdim=True)
        var = xg.var(dim=dims, unbiased=False, keepdim=True)
        if _GN["mode"] == "record":
            _GN["stats"][i] = (mean.detach().clone(), var.detach().clone())
    xn = ((xg - mean) * (var + self.eps).rsqrt()).view(x.shape)
    if self.weight is not None:
        shape = (1, Cc) + (1,) * (x.dim() - 2)
        xn = xn * self.weight.view(shape) + self.bias.view(shape)
    return xn


# ------------------------------------------------------------- inference
def _infer(model, dev, imgs, Ks, w2cs, dv, x0, y0, tw, th):
    sub = [im[:, y0:y0 + th, x0:x0 + tw].copy() for im in imgs]
    Kc = Ks.copy(); Kc[:, 0, 2] -= x0; Kc[:, 1, 2] -= y0
    proj = C.make_proj_matrices(Kc, w2cs)
    _CTX.update(x0=x0, y0=y0, tw=tw, th=th, draw=0)
    _GN["idx"] = 0
    return C.run_inference(model, sub, proj, dv, dev)


def _tile_rects(halo: int):
    out = []
    for gy in (0, 1):
        for gx in (0, 1):
            cx0, cy0 = gx * CORE_W, gy * CORE_H
            x0, y0 = max(0, cx0 - halo), max(0, cy0 - halo)
            x1, y1 = min(W, cx0 + CORE_W + halo), min(H, cy0 + CORE_H + halo)
            out.append(dict(x0=x0, y0=y0, tw=x1 - x0, th=y1 - y0, cx0=cx0, cy0=cy0))
    return out


def _stats(diff: np.ndarray) -> dict:
    return {"p50_mm": float(np.percentile(diff, 50) * 1000),
            "p95_mm": float(np.percentile(diff, 95) * 1000),
            "max_mm": float(diff.max() * 1000),
            "bitexact": bool(diff.max() == 0.0)}


def main() -> int:
    n_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    devp = sys.argv[2] if len(sys.argv) > 2 else "mps"
    out_json = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
        "/Users/kaidongwang/Documents/progecttwo/_host_fixtures/tile_gn_inject.json")

    dev = C.pick_device(devp)
    model, _ = C.build_model("casdiffmvs", dev)
    _, wdef, _ = PR._load_meta()
    picks = []
    for w in sorted(wdef.keys()):
        n = len(wdef[w]["frame_idx"])
        for r in (n // 6, n // 2, 5 * n // 6):
            picks.append((w, r))
    picks = picks[:n_frames]

    torch.set_grad_enabled(False)
    results = []
    t0 = time.time()

    for idx, (win, ref_local) in enumerate(picks):
        z = np.load(PR.EXPAC / "windows" / f"win_{win:02d}.npz")
        K_all, w2c_all = z["K"], z["w2c"]
        fidx = wdef[win]["frame_idx"]
        vl = PR.select_views(K_all, w2c_all, fidx, ref_local, N_VIEW)
        imgs = np.stack([PR.load_image(fidx[j]).transpose(2, 0, 1) for j in vl])
        Ks = np.stack([PR.scaled_K(K_all[j]) for j in vl])
        w2cs = np.stack([w2c_all[j].astype(np.float32) for j in vl])
        dmin, dmax = PR.metric_depth_range(fidx[vl[0]], w2cs[0])
        dv = C.depth_values_tensor(dmin, dmax)

        rec = {"win": win, "ref_local": ref_local}

        # 控制组 1:官方 GroupNorm 整图
        nn.GroupNorm.forward = _ORIG_GN_FORWARD
        _GN["mode"] = "off"
        d_official, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv, 0, 0, W, H)

        # 控制组 2:手写 GroupNorm(自算统计量)整图 —— 必须与官方逐位相同
        nn.GroupNorm.forward = _gn_forward
        _GN["mode"] = "off"
        d_manual, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv, 0, 0, W, H)
        rec["manual_vs_official_max_mm"] = float(np.abs(d_manual - d_official).max() * 1000)

        # record:整图跑一遍,记下每个 GroupNorm 的统计量
        _GN["mode"] = "record"; _GN["stats"] = {}
        d_whole, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv, 0, 0, W, H)
        rec["n_groupnorm_calls"] = len(_GN["stats"])

        rec["halos"] = {}
        for halo in HALOS:
            per_mode = {}
            for mode in ("off", "inject"):      # off = 老行为(tile 自算);inject = 注入整图统计量
                _GN["mode"] = mode; _GN["misses"] = 0
                stitched = np.zeros_like(d_whole)
                for t in _tile_rects(halo):
                    dt_, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv,
                                       t["x0"], t["y0"], t["tw"], t["th"])
                    sy, sx = t["cy0"] - t["y0"], t["cx0"] - t["x0"]
                    stitched[t["cy0"]:t["cy0"] + CORE_H, t["cx0"]:t["cx0"] + CORE_W] = \
                        dt_[sy:sy + CORE_H, sx:sx + CORE_W]
                diff = np.abs(stitched - d_whole)
                seam = np.zeros((H, W), bool)
                seam[CORE_H - SEAM_BAND:CORE_H + SEAM_BAND, :] = True
                seam[:, CORE_W - SEAM_BAND:CORE_W + SEAM_BAND] = True
                per_mode[mode] = {"all": _stats(diff.ravel()),
                                  "seam": _stats(diff[seam]),
                                  "interior": _stats(diff[~seam]),
                                  "gn_misses": _GN["misses"]}
            rec["halos"][str(halo)] = per_mode
        rec["noise_fallbacks"] = _CTX["fallbacks"]
        results.append(rec)

        h192 = rec["halos"]["192"]
        print(f"[{idx+1}/{len(picks)}] win{win:02d} ref{ref_local} "
              f"manual==official:{rec['manual_vs_official_max_mm']:.6f}mm "
              f"| GN calls={rec['n_groupnorm_calls']} "
              f"| h192 interior: 自算={h192['off']['interior']['p95_mm']:.1f} "
              f"注入={h192['inject']['interior']['p95_mm']:.2f}mm "
              f"({(time.time()-t0)/(idx+1):.0f}s/f)", flush=True)

        out_json.write_text(json.dumps({
            "config": {"H": H, "W": W, "n_view": N_VIEW, "halos": HALOS,
                       "device": str(dev), "frames_done": idx + 1},
            "peakRSS_GB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9,
            "results": results}, ensure_ascii=False, indent=2))

    nn.GroupNorm.forward = _ORIG_GN_FORWARD
    print(f"完成 {len(results)} 帧 -> {out_json}")
    return 0


if __name__ == "__main__":
    torch.randn_like = _canonical_randn_like
    raise SystemExit(main())
