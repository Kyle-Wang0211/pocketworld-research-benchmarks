#!/usr/bin/env python3
"""CoreML 上的 Conv3d 到底慢不慢?—— 决定"刀二"(3D→2D 融合)值不值得做。

背景:PyTorch/MPS 上实测 Conv3d 只跑到本机峰值的 3.6%,比同 FLOP 的 Conv2d 差 7.19×,
      把它融合成**单次** Conv2d 能快 3.98×。但产品跑 CoreML 不跑 MPS。
      **如果 CoreML 的 Conv3d 不慢,那把 11 个卷积全改写就是白干。** 本脚本先证伪。

方法:同一个 Conv3d(4→8,k3) 权重,导出两版 CoreML —
      A 原生 Conv3d
      B 融合版:沿 D 的 3 个移位堆进通道维 → 单次 Conv2d(12→8),FLOP 完全相同
      在 CPU_ONLY / CPU_AND_GPU / ALL(含 ANE)三档各测一遍。

⚠️ 只测一个卷积,不是整模型 —— 目的是**判据**不是端到端数字。整模型还有 warp/GRU,
   而且 CoreML 会做图级融合,端到端收益只会比这里的比值小,不会更大。
"""
import argparse, time
import numpy as np
import torch
import torch.nn.functional as F
import coremltools as ct

Cin, Cout, D, H, W = 4, 8, 48, 72, 96


class Native(torch.nn.Module):
    def __init__(self, c3):
        super().__init__()
        self.c = c3

    def forward(self, x):
        return self.c(x)


class Fused(torch.nn.Module):
    """Conv3d(k=3,pad=1) ≡ 单次 Conv2d(3*Cin→Cout),D 折进 batch、深度偏移堆进通道。"""
    def __init__(self, c3):
        super().__init__()
        w2 = c3.weight.permute(0, 2, 1, 3, 4).reshape(Cout, 3 * Cin, 3, 3).contiguous()
        self.c2 = torch.nn.Conv2d(3 * Cin, Cout, 3, padding=1)
        with torch.no_grad():
            self.c2.weight.copy_(w2)
            self.c2.bias.copy_(c3.bias)

    def forward(self, x):
        xb = x[0].permute(1, 0, 2, 3)                       # [D,Cin,H,W]
        z = torch.zeros_like(xb[:1])
        s = torch.cat([torch.cat([z, xb[:-1]], 0), xb,
                       torch.cat([xb[1:], z], 0)], 1)       # [D,3Cin,H,W]
        y = self.c2(s)
        return y.permute(1, 0, 2, 3).unsqueeze(0)


def to_mlmodel(mod, units):
    ex = torch.rand(1, Cin, D, H, W)
    ts = torch.jit.trace(mod.eval(), ex)
    return ct.convert(ts,
                      inputs=[ct.TensorType(name="x", shape=ex.shape)],
                      compute_units=units,
                      compute_precision=ct.precision.FLOAT16,
                      minimum_deployment_target=ct.target.iOS17)


def bench(m, x, n=30):
    d = {"x": x}
    for _ in range(5):
        m.predict(d)
    t0 = time.perf_counter()
    for _ in range(n):
        out = m.predict(d)
    return (time.perf_counter() - t0) / n * 1000, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=30)
    args = ap.parse_args()

    torch.manual_seed(0)
    c3 = torch.nn.Conv3d(Cin, Cout, 3, padding=1).eval()
    nat, fus = Native(c3).eval(), Fused(c3).eval()

    x = torch.randn(1, Cin, D, H, W)
    with torch.no_grad():
        r_nat, r_fus = nat(x), fus(x)
    print(f"torch 侧两版一致性:最大相对差 "
          f"{((r_nat-r_fus).abs().max()/r_nat.abs().max()).item():.2e}")
    gflop = 2 * Cin * Cout * 27 * D * H * W / 1e9
    print(f"该卷积 FLOP = {gflop:.3f} GFLOP  (两版完全相同)\n")

    xn = x.numpy().astype(np.float32)
    UNITS = [("CPU_ONLY", ct.ComputeUnit.CPU_ONLY),
             ("CPU_AND_GPU", ct.ComputeUnit.CPU_AND_GPU),
             ("ALL(含ANE)", ct.ComputeUnit.ALL)]
    print(f"{'计算单元':<16}{'Conv3d 原生':>16}{'融合 Conv2d':>16}{'提速':>9}")
    for name, u in UNITS:
        row = []
        for mod in (nat, fus):
            try:
                m = to_mlmodel(mod, u)
                t, out = bench(m, xn, args.iters)
                row.append((t, out))
            except Exception as e:
                row.append((None, str(e)[:70]))
        (t1, o1), (t2, o2) = row
        f1 = f"{t1:8.2f} ms {gflop/t1*1000:5.0f}G" if t1 else "🔴 转换失败"
        f2 = f"{t2:8.2f} ms {gflop/t2*1000:5.0f}G" if t2 else "🔴 转换失败"
        sp = f"{t1/t2:6.2f}×" if (t1 and t2) else "—"
        print(f"{name:<16}{f1:>16}{f2:>16}{sp:>9}")
        if t1 and t2:
            a = list(o1.values())[0]; b = list(o2.values())[0]
            mx = np.abs(a - b).max() / max(np.abs(a).max(), 1e-9)
            print(f"{'':16}两版输出最大相对差 {mx:.2e}")
        for t, o in row:
            if t is None:
                print(f"{'':16}⚠️ {o}")


if __name__ == "__main__":
    main()
