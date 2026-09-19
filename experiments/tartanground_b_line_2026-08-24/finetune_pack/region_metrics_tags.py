#!/usr/bin/env python3.11
"""region_metrics.py 的可参数化外壳:只把模块级常量 TAGS 换掉,其余零改动。

region_metrics.py 里 TAGS/TOLS 是模块级常量、main() 里当全局读,所以
import 之后直接改属性即可 —— 聚合逻辑、官方 voxel-cell 平均的复刻、
ALL-vs-official 自证全部原样执行,不复制一行算法代码。

用法:
    python3.11 region_metrics_tags.py --tags new,mytag --out /path/out.json
"""
import argparse
import importlib.util
import os
import json
import shutil
import sys
from pathlib import Path

RM = Path(os.environ.get("REGION_METRIC",
              "/Users/kaidongwang/Developer/ethd3d_a_line/region_metric_20260824"))


def load_module():
    spec = importlib.util.spec_from_file_location(
        "region_metrics_orig", RM / "region_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["region_metrics_orig"] = mod
    spec.loader.exec_module(mod)   # 模块名不是 __main__,不会触发 main()
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True, help="逗号分隔的 tag 列表")
    ap.add_argument("--out", required=True, help="把 region_results.json 复制到这里")
    a = ap.parse_args()

    tags = [t for t in a.tags.split(",") if t]
    mod = load_module()

    # 每个 tag 必须已经有 viz 点云 + eval_viz 日志
    for t in tags:
        for tol in mod.TOLS:
            for kind in ("comp", "acc"):
                p = mod.VIZ / f"{kind}_{t}.tolerance_{tol}.ply"
                if not p.exists():
                    sys.exit(f"[fatal] 缺少 {p} —— 先跑带 --*_cloud_output_path 的官方评测")
        lg = mod.LOGS / f"eval_viz_{t}.log"
        if not lg.exists():
            sys.exit(f"[fatal] 缺少 {lg}")

    mod.TAGS = tags
    print(f"[info] TAGS 覆盖为 {tags}(TOLS 保持官方 {mod.TOLS})")
    rc = mod.main()

    src = mod.CACHE / "region_results.json"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, a.out)
    # 把 tag 列表也记进去,渲染表格时用
    d = json.loads(Path(a.out).read_text())
    d["tags"] = tags
    Path(a.out).write_text(json.dumps(d, indent=2))
    print(f"[info] 结果 -> {a.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
