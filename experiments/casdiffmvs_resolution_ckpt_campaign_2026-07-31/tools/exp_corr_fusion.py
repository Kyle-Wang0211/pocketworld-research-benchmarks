#!/usr/bin/env python3
"""杠杆 1 隔离实验:stage-1 相关性块的三种实现,比峰值内存和耗时。

背景:module.py:616 把参考特征沿深度维 repeat 成一个 36P 的 `ref_volume`,
紧接着 :635 又乘出一个同样大的 `prod`,而 `prod` 乘完立刻被 mean 吃掉。
两个张量都不携带新信息 —— 一个是纯广播,一个是立即被规约的中间量。

把这个块单独拎出来测,是为了让测到的差异**百分之百**来自这个杠杆,不掺
FeatureNet/扩散/allocator 的噪声。

三种实现(数学上完全等价,必须逐一验数值):
  official  官方 EXPORT_MODE 路径: repeat -> 乘 -> reshape -> mean
  broadcast 不 repeat,靠广播: 省掉 ref_volume,但乘积仍然物化
  fused     einsum: 既不 repeat 也不物化乘积(走 bmm,逐块累加)

每个变体在**独立子进程**里跑,用 peak RSS 计量 —— 与端上 phys_footprint 同口径,
且 RSS 峰值是进程生命期单调量,同进程里连测多个变体会互相污染。

用法:
  exp_corr_fusion.py driver [896x512|4224x2400 ...]   # 跑全部变体并汇总
  exp_corr_fusion.py <variant> <W> <H>                # 子进程单跑(内部用)
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import time

import torch

# stage-1 特征金字塔:48 通道 @ H/8 x W/8;初始深度假设 48 层(不是 CLI 的 384,
# 后者只用于 refinement 的归一化间隔 —— 报告 A2 核对过)。
C_STAGE1 = 48
D_STAGE1 = 48
G = 8              # module.py:569 group_dim 默认 8
REPEATS = 3        # 每个变体重复 3 次取中位,避免单次计时不可信


def _peak_rss_mb() -> float:
    # macOS 的 ru_maxrss 单位是 byte(Linux 是 KB)
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576.0


def official(warped, ref_feat, B, C, D, H, W):
    """module.py:616 + :635-636 逐字复刻(EXPORT_MODE 分支,也就是我们导出走的那条)。"""
    ref_volume = ref_feat.unsqueeze(2).repeat(1, 1, D, 1, 1)          # 36P 物化
    prod = (warped * ref_volume).reshape(B * G, C // G, D, H, W)      # 又一个 36P
    return prod.mean(1).reshape(B, G, D, H, W)


def broadcast(warped, ref_feat, B, C, D, H, W):
    """只去掉 repeat:ref 靠广播参与运算,乘积仍然物化。"""
    ref_b = ref_feat.unsqueeze(2)                                     # (B,C,1,H,W) 广播
    prod = (warped * ref_b).reshape(B * G, C // G, D, H, W)
    return prod.mean(1).reshape(B, G, D, H, W)


def fused(warped, ref_feat, B, C, D, H, W):
    """既不 repeat 也不物化乘积:组内对 C/G 做点积,einsum 走 bmm 直接累加。"""
    w5 = warped.view(B, G, C // G, D, H * W)
    r4 = ref_feat.view(B, G, C // G, H * W)
    return torch.einsum('bgcdp,bgcp->bgdp', w5, r4).view(B, G, D, H, W) / (C // G)


VARIANTS = {"official": official, "broadcast": broadcast, "fused": fused}


def run_variant(name: str, W: int, H: int) -> dict:
    torch.set_grad_enabled(False)
    torch.manual_seed(0)
    B, C, D = 1, C_STAGE1, D_STAGE1
    h, w = H // 8, W // 8                       # stage-1 在 1/8 分辨率上
    base = _peak_rss_mb()
    warped = torch.randn(B, C, D, h, w)
    ref_feat = torch.randn(B, C, h, w)
    after_inputs = _peak_rss_mb()

    fn = VARIANTS[name]
    ts = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        out = fn(warped, ref_feat, B, C, D, h, w)
        ts.append((time.perf_counter() - t0) * 1000)
        del out
    ts.sort()

    out = fn(warped, ref_feat, B, C, D, h, w)
    return {
        "variant": name, "W": W, "H": H, "stage1_hw": [h, w],
        "input_MB": round(after_inputs - base, 1),
        "peak_rss_MB": round(_peak_rss_mb(), 1),
        "delta_over_inputs_MB": round(_peak_rss_mb() - after_inputs, 1),
        "ms_median": round(ts[len(ts) // 2], 1),
        "out_sum": float(out.double().sum()),     # 数值等价性指纹
        "out_shape": list(out.shape),
    }


def driver(sizes) -> int:
    me = os.path.abspath(__file__)
    all_rows = []
    for s in sizes:
        Wd, Hd = (int(x) for x in s.lower().split("x"))
        rows = []
        for name in VARIANTS:
            r = subprocess.run([sys.executable, me, name, str(Wd), str(Hd)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[{s} {name}] 失败:\n{r.stderr[-600:]}")
                continue
            rows.append(json.loads(r.stdout.strip().splitlines()[-1]))
        if not rows:
            continue
        ref_sum = rows[0]["out_sum"]
        print(f"\n=== {s}  (stage-1 grid {rows[0]['stage1_hw'][0]}x{rows[0]['stage1_hw'][1]}, "
              f"C={C_STAGE1} D={D_STAGE1} G={G}) ===")
        print(f"{'变体':<10} {'峰值RSS':>10} {'扣掉输入':>10} {'耗时中位':>10}   数值等价")
        for r in rows:
            rel = abs(r["out_sum"] - ref_sum) / max(abs(ref_sum), 1e-9)
            print(f"{r['variant']:<10} {r['peak_rss_MB']:>9.1f}MB {r['delta_over_inputs_MB']:>9.1f}MB "
                  f"{r['ms_median']:>9.1f}ms   相对差 {rel:.2e}")
        base_peak = rows[0]["peak_rss_MB"]
        for r in rows[1:]:
            print(f"  -> {r['variant']:<9} 省 {base_peak - r['peak_rss_MB']:6.1f}MB "
                  f"({(1 - r['peak_rss_MB']/base_peak)*100:5.1f}%)  "
                  f"速度 {rows[0]['ms_median']/max(r['ms_median'],1e-9):.2f}x")
        all_rows.extend(rows)
    out = "/Users/kaidongwang/Documents/progecttwo/_host_fixtures/corr_fusion.json"
    with open(out, "w") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "driver":
        raise SystemExit(driver(sys.argv[2:] or ["896x512"]))
    print(json.dumps(run_variant(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))))
