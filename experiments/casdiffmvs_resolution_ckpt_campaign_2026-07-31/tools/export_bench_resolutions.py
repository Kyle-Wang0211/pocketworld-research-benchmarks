#!/usr/bin/env python3
"""把 CasDiffMVS 导成**多个分辨率**的 CoreML 包,供真机 bench 实测速度/峰值内存。

背景:"12MP 直喂行不行"此前只有线性外推,没有测量。模型输入形状是 trace 死的,
换分辨率必须重导 —— 所以先批量产模型,再让 DiffMVSBench 在真机上逐个打。

刻意只改**输入形状**,其余(fp32、CPU_AND_GPU、iOS17 target、checkpoint)全部沿用
pw_export_coreml.py 的生产设定。bench 用随机张量,所以不需要真实 npz/图像。

用法:
  /opt/homebrew/bin/python3.11 export_bench_resolutions.py <输出目录> [WxH ...]
不给尺寸就用内置清单。尺寸必须 W、H 都能被 32 整除(模型硬要求)。
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

RESEARCH = Path.home() / (
    "Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python"
)
sys.path.insert(0, str(RESEARCH))

import coremltools as ct  # noqa: E402
import torch  # noqa: E402

import pw_diffmvs_common as C  # noqa: E402


def _apply_production_patches() -> None:
    """生产导出脚本里那两个必需补丁,原文取用不重写。

    少了它们 coremltools 会在 depthnet 处炸 "only 0-dimensional arrays can be
    converted to Python scalars"(numpy2 下 aten::Int 的转换 bug)。
    """
    import numpy as np

    src = (RESEARCH / "pw_export_coreml.py").read_text().splitlines()
    # 补丁函数体内部引用 torch/nn/np/ct —— exec 的 globals 必须给全,
    # 否则报 NameError 而不是真正的转换错误(踩过)。
    ns: dict = {"torch": torch, "nn": torch.nn, "np": np, "ct": ct}
    for fn in ("patch_coremltools_numpy2", "patch_batchnorm3d"):
        start = next(i for i, l in enumerate(src) if l.startswith(f"def {fn}("))
        end = start + 1
        while end < len(src) and (src[end].startswith((" ", "\t")) or not src[end].strip()):
            end += 1
        exec("\n".join(src[start:end]), ns)
    ns["patch_coremltools_numpy2"]()
    ns["patch_batchnorm3d"]()

    # module.EXPORT_MODE 打开的是 gather-free 置信度 + 那个 ConvTranspose3d
    # output_padding 的重写(coremltools 只支持 1D/2D 的 output_padding)。
    # 不开的话直接炸 "output_padding is supported only for ConvTranspose1D/2D"。
    import models.module as mod  # noqa: E402
    mod.EXPORT_MODE = True

# 默认梯子:'o' 基线 → 4:3 同像素 → 官方分辨率 → 一路逼近 12MP。
# 4032×3024 的 3024 不能被 32 整除(94.5),最接近的合法高度是 3008。
DEFAULT_LADDER = [
    (896, 512),    # 'o' 认证基线(16:9-ish)
    (768, 576),    # 4:3,像素数与 'o' 基本相同
    (896, 672),    # 4:3
    (1024, 768),   # 4:3
    (1280, 960),   # 4:3
    (1600, 1152),  # 官方 CasDiffMVS 分辨率
    (2048, 1536),  # 4:3
    (2688, 2016),  # 4:3
    (4032, 3008),  # 12MP 原尺寸(高度取最近的 32 倍数)
]

NVIEW = 5


class Wrap(torch.nn.Module):
    """与 pw_export_coreml.py 逐字相同的 forward 包装。"""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, i0, i1, i2, i3, i4, p1, p2, p3, p4, dvv):
        o = self.m([i0, i1, i2, i3, i4],
                   {"stage1": p1, "stage2": p2, "stage3": p3, "stage4": p4}, dvv)
        return o["depth"][-1], o["photometric_confidence"][-1]


def export_one(model, w: int, h: int, out_dir: Path) -> dict:
    assert w % 32 == 0 and h % 32 == 0, f"{w}x{h} 不是 32 的倍数,模型不接受"
    imgs = [torch.rand(1, 3, h, w) for _ in range(NVIEW)]
    proj = [torch.rand(1, NVIEW, 2, 4, 4) for _ in range(4)]
    dv = torch.rand(1, 384)
    ins = (*imgs, *proj, dv)
    names = ["i0", "i1", "i2", "i3", "i4", "p1", "p2", "p3", "p4", "dv"]

    rec: dict = {"w": w, "h": h}
    t0 = time.time()
    try:
        wrapped = Wrap(model).eval()
        with torch.no_grad():
            tr = torch.jit.trace(wrapped, ins, check_trace=False)
        ml = ct.convert(
            tr,
            inputs=[ct.TensorType(name=n, shape=x.shape) for n, x in zip(names, ins)],
            minimum_deployment_target=ct.target.iOS17,
            compute_units=ct.ComputeUnit.CPU_AND_GPU,
            # PW_FP16=1 -> 权重与中间计算都走 fp16。默认仍是 FLOAT32,与已导出的
            # 9 档逐字一致,便于 A/B(fp16 是"近无损"不是无损,质量必须单独验)。
            compute_precision=(ct.precision.FLOAT16 if os.environ.get("PW_FP16") == "1"
                               else ct.precision.FLOAT32),
            # 转完**不要**在 Mac 上把模型 load 进 CoreML runtime:那一步会再拿一份
            # 权重+编译产物,是 2688x2016 那档把 18GB 撑爆的放大器之一。我们本来就
            # 只在真机上跑它,Mac 侧的 load 没有任何用处。存出来的包逐字节不受影响。
            skip_model_load=True,
        )
        pkg = out_dir / f"CasDiffMVS_{w}x{h}.mlpackage"
        shutil.rmtree(pkg, ignore_errors=True)
        ml.save(str(pkg))
        mb = sum(os.path.getsize(os.path.join(dp, f))
                 for dp, _, fs in os.walk(pkg) for f in fs) / 1e6
        rec.update(ok=True, mb=round(mb, 2), secs=round(time.time() - t0, 1))
    except Exception as e:  # 导不出来本身就是结论 —— 记下来,别让整批停摆
        rec.update(ok=False, error=f"{type(e).__name__}: {e}"[:400],
                   secs=round(time.time() - t0, 1))
    return rec


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    ladder = DEFAULT_LADDER
    if len(sys.argv) > 2:
        ladder = []
        for a in sys.argv[2:]:
            w, h = a.lower().split("x")
            ladder.append((int(w), int(h)))

    _apply_production_patches()
    model, _ = C.build_model("casdiffmvs", torch.device("cpu"))
    print(f"[export] {len(ladder)} 个分辨率 -> {out_dir}", flush=True)

    log = out_dir / "export_log.txt"
    for w, h in ladder:
        px = w * h / 1e6
        print(f"[export] {w}x{h}  ({px:.2f} Mpx, {px / 0.458752:.1f}x 'o') ...",
              flush=True)
        rec = export_one(model, w, h, out_dir)
        line = (f"{w}x{h}\tMpx={px:.3f}\tok={rec['ok']}\t"
                f"{'MB=' + str(rec.get('mb')) if rec['ok'] else rec.get('error')}\t"
                f"{rec['secs']}s")
        print("   " + line, flush=True)
        with log.open("a") as f:
            f.write(line + "\n")
    print(f"[export] 完成,日志 {log}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
