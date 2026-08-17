#!/usr/bin/env python3
"""138 帧稀疏点真值评测 —— 与 APDe 对比用的同一把尺子。

⚠️ 原始脚本写在 /tmp 里已随系统清理丢失。本文件是重建版,
   **必须先通过自校验**(复现已知的 base / ofull15 数字)才允许用它下结论。

口径:
  帧集   = 413 帧按 stride 3 取的 138 帧子集(与 make_subset.py 一致)
  真值   = trio_model_lapa.npz 的稀疏点,按各帧观测表投影
  覆盖率 = 该帧观测点里"预测深度 > 0"的比例
  <1%/<5% = **在被覆盖的点里**,相对误差 |z_pred-z_true|/z_true 小于阈值的比例
"""
from __future__ import annotations
import sys
import numpy as np

R = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs_out"
STRIDE = 3


def load_gt():
    z = np.load(f"{R}/trio_model_lapa.npz", allow_pickle=True)
    return z["K"], z["w2c"], z["pts"], z["obs_idx"], z["obs_off"], z["names"]


def evaluate(dm, sel, K, w2c, pts, oi, oo, W=896, H=512):
    n_all = n_cov = n1 = n5 = 0
    for f in sel:
        idx = oi[oo[f]:oo[f + 1]]
        if len(idx) == 0:
            continue
        X = pts[idx]
        Xc = (w2c[f][:3, :3] @ X.T).T + w2c[f][:3, 3]
        zt = Xc[:, 2]
        m = zt > 1e-6
        Xc, zt = Xc[m], zt[m]
        uvw = (K[f] @ Xc.T).T
        u = np.round(uvw[:, 0] / uvw[:, 2]).astype(int)
        v = np.round(uvw[:, 1] / uvw[:, 2]).astype(int)
        inb = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        u, v, zt = u[inb], v[inb], zt[inb]
        zp = dm[f][v, u]
        cov = zp > 0
        rel = np.abs(zp[cov] - zt[cov]) / zt[cov]
        n_all += len(zt); n_cov += int(cov.sum())
        n1 += int((rel < 0.01).sum()); n5 += int((rel < 0.05).sum())
    return dict(pts=n_all,
                cov=100.0 * n_cov / max(n_all, 1),
                lt1=100.0 * n1 / max(n_cov, 1),
                lt5=100.0 * n5 / max(n_cov, 1))


def main() -> int:
    K, w2c, pts, oi, oo, names = load_gt()
    sel = list(range(0, len(names), STRIDE))
    print(f"帧集 {len(sel)} 帧(stride={STRIDE},共 {len(names)} 帧)\n")

    # ── 自校验:必须复现历史数字,否则尺子不同,结论不可比 ──
    EXPECT = {"base": (51.0, 82.7, 99.7), "ofull15": (51.6, 91.5, 99.7)}
    print(f"{'档位':<12}{'覆盖':>8}{'<1%':>8}{'<5%':>8}   自校验")
    ok = True
    for tag, (ec, e1, e5) in EXPECT.items():
        d = np.load(f"{R}/dmcache_trio_{tag}.npz", allow_pickle=True)
        r = evaluate(d["dm"], sel, K, w2c, pts, oi, oo)
        dc, d1, d5 = abs(r["cov"]-ec), abs(r["lt1"]-e1), abs(r["lt5"]-e5)
        good = dc < 1.0 and d1 < 1.5 and d5 < 1.0
        ok &= good
        print(f"{tag:<12}{r['cov']:7.1f}%{r['lt1']:7.1f}%{r['lt5']:7.1f}%   "
              f"{'✅' if good else '🔴'} 期望 {ec}/{e1}/{e5}")
    if not ok:
        print("\n🔴 自校验未通过 —— 重建的指标与历史口径不同,**不能用它下结论**。")
        return 2
    print("\n✅ 自校验通过:重建的指标复现了历史数字,尺子一致。\n")

    for p in sys.argv[1:]:
        d = np.load(p, allow_pickle=True)
        dm = d["dm"] if "dm" in d.files else d[d.files[0]]
        r = evaluate(dm, sel, K, w2c, pts, oi, oo)
        print(f"{p.split('/')[-1]:<34}{r['cov']:7.1f}%{r['lt1']:7.1f}%{r['lt5']:7.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
