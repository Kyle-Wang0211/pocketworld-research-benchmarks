#!/usr/bin/env python3
"""三臂稠密云的覆盖 + 表面粗糙度。两把尺子都 **import 现成实现**,不重写。

  coverage:  lightglue_spike/coverage_metric.py  的 read_ply / occupied
  roughness: lightglue_spike/local_roughness.py  的 local_roughness(k=15)
             ↑ 这是 08-17 唯一被用户肉眼判决校准过的粗糙度尺子(排序与肉眼完全一致),
               自己新写一把等于丢掉那次校准。

⚠️ **故意不用 coverage_metric.knn_spread**:它是暴力 O(sample×N) 且中间矩阵是
   (512, N) —— 为 24 万点的稀疏云设计。本任务的稠密云 N≈3000 万,该矩阵 123 GB,
   必然 OOM。它想回答的"面有多实",局部 PCA 粗糙度回答得更好,不补第二把。

⚠️ **不报 `<1%` 精度**:b28 是真实拍摄没有深度真值;且历史上该指标只在稀疏 SfM 点
   上测,对白墙/地板等无纹理区是结构性盲区,曾被肉眼推翻。

前置:非参考臂必须先过 apply_gauge.py。
"""
import argparse, gc, importlib.util, json, os, sys, tempfile
import numpy as np

SPIKE = os.path.expanduser("~/Documents/progecttwo/_artifacts/lightglue_spike")


def _load(mod):
    """按路径加载。local_roughness.py 顶层有个 CLI 循环,在空目录里 import 它只会
       打印 8 行"缺文件"然后结束 —— 无副作用,换取的是函数逐字来自原件。"""
    spec = importlib.util.spec_from_file_location(mod, f"{SPIKE}/{mod}.py")
    m = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            spec.loader.exec_module(m)
        finally:
            os.chdir(cwd)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--ref", default="P16k")
    ap.add_argument("--arms", default="P16k,P8k,P16kH")
    ap.add_argument("--voxels", default="0.02,0.05,0.10,0.20")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    print("加载现成尺子…", flush=True)
    cov_m = _load("coverage_metric")
    rgh_m = _load("local_roughness")
    sizes = [float(x) for x in a.voxels.split(",")]
    arms = a.arms.split(",")

    res = {}
    for w in arms:
        # 参考臂用原云;其余臂用 gauge 对齐后的云
        p = f"{a.dir}/dense_{w}.ply" if w == a.ref else f"{a.dir}/aligned_{w}.ply"
        xyz = cov_m.read_ply(p)
        r = {"points": len(xyz),
             "coverage": {s: int(cov_m.occupied(xyz, s)) for s in sizes}}
        print(f"  {w} 覆盖完成 ({len(xyz):,} 点)", flush=True)
        rg = rgh_m.local_roughness(xyz) * 1000.0            # → mm,k=15 全量点
        r.update(rough_p50=float(np.median(rg)), rough_p75=float(np.percentile(rg, 75)),
                 rough_p90=float(np.percentile(rg, 90)),
                 rough_gt10=float((rg > 10).mean() * 100), rough_gt20=float((rg > 20).mean() * 100),
                 pts_per_vox=len(xyz) / max(r["coverage"][sizes[1]], 1))
        res[w] = r
        print(f"  {w} 粗糙度完成  中位 {r['rough_p50']:.2f}mm", flush=True)
        del xyz, rg; gc.collect()

    hdr = (f"\n{'臂':<8}{'点数':>12}" + "".join(f"{'占据'+str(s)+'m':>12}" for s in sizes)
           + f"{'点/格':>8}{'粗糙p50':>9}{'p75':>8}{'p90':>8}{'>10mm':>8}{'>20mm':>8}")
    print(hdr)
    for w in arms:
        r = res[w]
        print(f"  {w:<6}{r['points']:>12,}" + "".join(f"{r['coverage'][s]:>12,}" for s in sizes)
              + f"{r['pts_per_vox']:>8.1f}{r['rough_p50']:>9.2f}{r['rough_p75']:>8.2f}"
              + f"{r['rough_p90']:>8.2f}{r['rough_gt10']:>7.2f}%{r['rough_gt20']:>7.2f}%")

    base = res[a.ref]
    print(f"\n相对 {a.ref}:")
    for w in arms:
        if w == a.ref: continue
        r = res[w]
        tag = "噪声地板" if w.endswith("H") else "预算效应"
        print(f"  {w:<6}({tag})  点数 {100*(r['points']/base['points']-1):+6.2f}%   覆盖 "
              + " ".join(f"{s}m {100*(r['coverage'][s]/base['coverage'][s]-1):+6.2f}%" for s in sizes)
              + f"   粗糙p50 {100*(r['rough_p50']/base['rough_p50']-1):+6.2f}%")
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
