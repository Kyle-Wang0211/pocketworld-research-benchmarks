#!/usr/bin/env python3
"""whole-vs-tile 数值对照:把 FULLRES 报告里 halo 的**静态下界 188px** 换成实测曲线。

背景:operator 级分块是唯一"理论无损"的降峰值路线,但 2026-07-21 的报告把它判为
UNVERIFIED —— 仓库里搜不到任何实现或实验。这是那条路的第一步,也是最便宜的一步:
不写 operator scheduler,只在**能放下整图**的 896x512 上做等价性对照。

问的问题只有一个:**误差随 halo 增大是趋于 0,还是停在一个非零地板上?**
 - 趋于 0 → model-call 级分块可以做到等价,后面才值得投 operator scheduler 的工。
 - 停在地板 → 源视图 ROI 的非局部性(报告 A2 第 1 条)无法靠同窗口 halo 补偿,
   model-call 级分块**构造性不可能**等价,必须直接上 operator 级或放弃这条路。

三个必须做对的地方(报告 A2 逐条点过的机关):
 1. **canonical noise**。扩散用 torch.randn_like,tile 化会改变 RNG 消耗顺序,
    不处理的话 whole/tile 必然不同,且那个差异跟 halo 无关 —— 会把真信号淹掉。
    这里预生成"全图坐标系"的噪声场,按 tile 的全局偏移切片,whole 和 tile 拿到
    逐元素相同的噪声。第 k 次抽样用第 k 个场,保证两边抽样序列对齐。
 2. **内参必须跟着 crop 走**。cx-=x0, cy-=y0;偏移取 32 的倍数,保证 stage 缩放
    (最小 0.125)后仍落在整数网格上,不引入半像素偏差。
 3. **自洽性对照**。先把整图跑两遍比对 —— 若同一输入两遍就不逐位相同,那么
    tile 的差异低于这个噪声底就没有意义。没有这个控制组,整个实验不可解释。

用法: exp_tile_vs_whole.py [N_FRAMES] [DEVICE] [OUT_JSON]
"""
from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import torch

RESEARCH = Path.home() / "Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python"
sys.path.insert(0, str(RESEARCH))

import pw_diffmvs_common as C      # noqa: E402
import pw_diffmvs_run as PR        # noqa: E402

H, W = PR.PROC_H, PR.PROC_W        # 512, 896
N_VIEW = 5                         # 与端上导出的 NVIEW 一致
CORE_H, CORE_W = H // 2, W // 2    # 2x2 切分 -> 每块核心 256x448
HALOS = [0, 32, 64, 128, 192]      # 192 > 报告的静态下界 188
HALOS_B = [0, 64, 192]             # 模式 B 只做归因,三个点够看趋势
SEAM_BAND = 16                     # 距内部核心边界 <=16px 记为 seam band

# ---------------------------------------------------------------- canonical noise
_ORIG_RANDN_LIKE = torch.randn_like
_CTX = {"x0": 0, "y0": 0, "tw": W, "th": H, "draw": 0, "fields": {}, "fallbacks": 0}


def _field(draw: int, s: int) -> torch.Tensor:
    """第 draw 次抽样、缩放系数 s 的全图噪声场。种子只依赖 (draw,s),所以 whole 和
    tile 两次运行拿到的是同一个场 —— 这正是"canonical"的含义。"""
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
    draw = _CTX["draw"]
    _CTX["draw"] += 1
    # 只接管"空间形状能整除对上"的抽样;其余原样放行并计数(计数不为 0 就说明
    # 有没被 canonical 化的随机源,结论必须打折 —— 所以要报出来而不是静默)。
    if h == 0 or w == 0 or th % h or tw % w or (th // h) != (tw // w):
        _CTX["fallbacks"] += 1
        return _ORIG_RANDN_LIKE(t, *a, **k)
    s = th // h
    y0s, x0s = _CTX["y0"] // s, _CTX["x0"] // s
    sl = _field(draw, s)[y0s:y0s + h, x0s:x0s + w]
    view = sl.reshape((1,) * (len(shape) - 2) + (h, w))
    return view.expand(shape).to(device=t.device, dtype=t.dtype).contiguous()


def _set_ctx(x0: int, y0: int, tw: int, th: int) -> None:
    _CTX.update(x0=x0, y0=y0, tw=tw, th=th, draw=0)


# ---------------------------------------------------------------- one inference
def _infer(model, dev, imgs, Ks, w2cs, dv, x0, y0, tw, th, crop_sources=True):
    """imgs: (N,3,H,W) 全图;按 (x0,y0,tw,th) 裁块。

    crop_sources=True(模式 A,近似工程档):**所有视图**一起裁。参考块需要的源区域
      是投影并集,不等于同坐标矩形 —— 误差地板若存在就来自这里。
    crop_sources=False(模式 B,归因对照):只裁参考,源视图给全图、内参不动。
      differentiable_warping 的 height/width 取自 src_fea.shape,与参考网格
      height0/width0 解耦,所以数值上成立;FeatureNet 对每个视图独立、结果存 list
      而不是 stack,所以尺寸不同也跑得通。
      模式 B 里剩下的误差只可能来自卷积边界/上下文,不可能来自源 ROI ——
      两个模式一减,就把"内部误差"归因钉死了。
    """
    if crop_sources:
        sub = [im[:, y0:y0 + th, x0:x0 + tw].copy() for im in imgs]
    else:
        sub = [imgs[0][:, y0:y0 + th, x0:x0 + tw].copy()] + \
              [im.copy() for im in imgs[1:]]
    Kc = Ks.copy()
    n_adj = Ks.shape[0] if crop_sources else 1
    Kc[:n_adj, 0, 2] -= x0
    Kc[:n_adj, 1, 2] -= y0
    proj = C.make_proj_matrices(Kc, w2cs)
    _set_ctx(x0, y0, tw, th)
    depth, conf, dt = C.run_inference(model, sub, proj, dv, dev)
    return depth, conf, dt


def _tile_rects(halo: int):
    """2x2 核心 + halo,越界侧自动截断(与整图在该侧的边界条件一致)。"""
    out = []
    for gy in (0, 1):
        for gx in (0, 1):
            cx0, cy0 = gx * CORE_W, gy * CORE_H
            x0 = max(0, cx0 - halo)
            y0 = max(0, cy0 - halo)
            x1 = min(W, cx0 + CORE_W + halo)
            y1 = min(H, cy0 + CORE_H + halo)
            assert (x1 - x0) % 32 == 0 and (y1 - y0) % 32 == 0, (x0, x1, y0, y1)
            out.append(dict(x0=x0, y0=y0, tw=x1 - x0, th=y1 - y0,
                            cx0=cx0, cy0=cy0))
    return out


def _stats(diff: np.ndarray, ref: np.ndarray) -> dict:
    if diff.size == 0:
        return {}
    rel = diff / np.maximum(ref, 1e-6)
    return {
        "p50_mm": float(np.percentile(diff, 50) * 1000),
        "p95_mm": float(np.percentile(diff, 95) * 1000),
        "p99_mm": float(np.percentile(diff, 99) * 1000),
        "max_mm": float(diff.max() * 1000),
        "mean_rel_pct": float(rel.mean() * 100),
        "frac_gt1pct": float((rel > 0.01).mean()),
        "bitexact": bool(diff.max() == 0.0),
    }


def main() -> int:
    n_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    devp = sys.argv[2] if len(sys.argv) > 2 else "mps"
    out_json = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
        "/Users/kaidongwang/Documents/progecttwo/_host_fixtures/tile_vs_whole.json")

    dev = C.pick_device(devp)
    model, _ = C.build_model("casdiffmvs", dev)
    man, wdef, _ = PR._load_meta()
    wins = sorted(wdef.keys())

    # 100 个参考帧跨窗口铺开(每窗 3 个,窗内均匀),确定性、可复现。
    picks = []
    for w in wins:
        n = len(wdef[w]["frame_idx"])
        for r in (n // 6, n // 2, 5 * n // 6):
            picks.append((w, r))
    picks = picks[:n_frames]

    torch.set_grad_enabled(False)
    results = []
    t_start = time.time()

    for idx, (win, ref_local) in enumerate(picks):
        z = np.load(PR.EXPAC / "windows" / f"win_{win:02d}.npz")
        K_all, w2c_all = z["K"], z["w2c"]
        fidx = wdef[win]["frame_idx"]
        vl = PR.select_views(K_all, w2c_all, fidx, ref_local, N_VIEW)
        imgs = np.stack([PR.load_image(fidx[j]).transpose(2, 0, 1) for j in vl])
        Ks = np.stack([PR.scaled_K(K_all[j]) for j in vl])
        w2cs = np.stack([w2c_all[j].astype(np.float32) for j in vl])
        dmin, dmax = PR.metric_depth_range(fidx[vl[0]], w2cs[0])
        dv = C.depth_values_tensor(dmin, dmax)      # 全局深度范围,tile 之间不变

        rec = {"win": win, "ref_local": ref_local, "dmin": dmin, "dmax": dmax}

        # --- 控制组:同一输入跑两遍。不逐位相同的话,后面所有差异都不可解释 ---
        d_whole, c_whole, _ = _infer(model, dev, imgs, Ks, w2cs, dv, 0, 0, W, H)
        if idx < 5:
            d2, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv, 0, 0, W, H)
            rec["selfcheck_max_mm"] = float(np.abs(d_whole - d2).max() * 1000)

        # --- halo 扫描:模式 A(全裁) + 模式 B(只裁参考,归因对照) ---
        rec["halos"] = {}
        rec["halosB"] = {}
        for mode, halos, bucket in (("A", HALOS, rec["halos"]),
                                    ("B", HALOS_B, rec["halosB"])):
          for halo in halos:
            stitched = np.zeros_like(d_whole)
            for t in _tile_rects(halo):
                dt_, _, _ = _infer(model, dev, imgs, Ks, w2cs, dv,
                                   t["x0"], t["y0"], t["tw"], t["th"],
                                   crop_sources=(mode == "A"))
                # 只取核心区,halo 部分整块丢弃
                sy = t["cy0"] - t["y0"]
                sx = t["cx0"] - t["x0"]
                stitched[t["cy0"]:t["cy0"] + CORE_H, t["cx0"]:t["cx0"] + CORE_W] = \
                    dt_[sy:sy + CORE_H, sx:sx + CORE_W]

            diff = np.abs(stitched - d_whole)
            seam = np.zeros((H, W), bool)
            seam[CORE_H - SEAM_BAND:CORE_H + SEAM_BAND, :] = True
            seam[:, CORE_W - SEAM_BAND:CORE_W + SEAM_BAND] = True
            bucket[str(halo)] = {
                "all": _stats(diff.ravel(), d_whole.ravel()),
                "seam": _stats(diff[seam], d_whole[seam]),
                "interior": _stats(diff[~seam], d_whole[~seam]),
                "core_frac": float(CORE_H * CORE_W * 4 / (H * W)),
                "tile_px_per_core_px": float(
                    sum(t["tw"] * t["th"] for t in _tile_rects(halo)) / (H * W)),
            }
        rec["noise_fallbacks"] = _CTX["fallbacks"]
        results.append(rec)

        done = idx + 1
        el = time.time() - t_start
        print(f"[{done}/{len(picks)}] win{win:02d} ref{ref_local} "
              f"A: h0={rec['halos']['0']['all']['p95_mm']:.1f} "
              f"h192={rec['halos']['192']['all']['p95_mm']:.1f} "
              f"(interior {rec['halos']['192']['interior']['p95_mm']:.1f}) | "
              f"B: h192={rec['halosB']['192']['all']['p95_mm']:.1f} "
              f"(interior {rec['halosB']['192']['interior']['p95_mm']:.1f}) mm "
              f"({el/done:.0f}s/f)", flush=True)

        out_json.write_text(json.dumps({          # 逐帧落盘,中途挂了也留得下
            "config": {"H": H, "W": W, "n_view": N_VIEW, "halos": HALOS, "halosB": HALOS_B,
                       "core": [CORE_H, CORE_W], "seam_band": SEAM_BAND,
                       "device": str(dev), "frames_done": done},
            "peakRSS_GB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9,
            "results": results,
        }, ensure_ascii=False, indent=2))

    print(f"完成 {len(results)} 帧,峰值 RSS "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9:.2f} GB -> {out_json}")
    return 0


if __name__ == "__main__":
    torch.randn_like = _canonical_randn_like     # 全局接管,只在本进程内生效
    raise SystemExit(main())
