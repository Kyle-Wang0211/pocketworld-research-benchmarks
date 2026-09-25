#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

import numpy as np


PAGE = Path(__file__).resolve().parent
ROOT = PAGE.parents[3]
PLY = (
    ROOT
    / "_host_experiments.nosync/mapanything_apache_b28_official_image_only_20260826.nosync"
    / "points.ply"
)
DTYPE = np.dtype(
    [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("r", "u1"), ("g", "u1"), ("b", "u1"), ("a", "u1"),
    ]
)


def ply_layout(path: Path) -> tuple[int, int]:
    count = None
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if line.startswith(b"element vertex "):
                count = int(line.split()[-1])
            if line.strip() == b"end_header":
                offset = stream.tell()
                break
            if not line:
                raise ValueError("Incomplete PLY header")
    if count is None or path.stat().st_size != offset + count * DTYPE.itemsize:
        raise ValueError("Unexpected official PLY layout")
    return count, offset


def build_bins(path: Path) -> dict:
    count, offset = ply_layout(path)
    records = np.memmap(path, dtype=DTYPE, mode="r", offset=offset, shape=(count,))
    pos_path = PAGE / "bin/mapanything_official.pos"
    col_path = PAGE / "bin/mapanything_official.col"
    pos_path.parent.mkdir(parents=True, exist_ok=True)
    sample_stride = max(1, count // 500_000)
    samples = []
    with pos_path.open("wb") as pos_out, col_path.open("wb") as col_out:
        for start in range(0, count, 1_000_000):
            block = records[start : start + 1_000_000]
            xyz = np.column_stack((block["x"], block["y"], block["z"])).astype("<f4")
            rgb = np.column_stack((block["r"], block["g"], block["b"])).astype("u1")
            np.ascontiguousarray(xyz).tofile(pos_out)
            np.ascontiguousarray(rgb).tofile(col_out)
            samples.append(xyz[(-start) % sample_stride :: sample_stride].copy())
    sample = np.concatenate(samples)
    lo, hi = np.percentile(sample, [1, 99], axis=0)
    median = np.median(sample, axis=0)
    radius = float(np.percentile(np.linalg.norm(sample - median, axis=1), 95))
    return {
        "n": count,
        "center": ((lo + hi) / 2).astype(float).tolist(),
        "ext": (hi - lo).astype(float).tolist(),
        "med": median.astype(float).tolist(),
        "radius": radius,
    }


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


meta = build_bins(PLY)
(PAGE / "bin/meta.json").write_text(
    json.dumps({"mapanything_official": meta}, indent=2) + "\n"
)
template = load_module("fullres_builder", PAGE.parent / "build_page_fullres.py").TPL
view = {"cx": meta["med"][0], "cy": meta["med"][1], "cz": meta["med"][2], "radius": meta["radius"]}
plan = [[
    "MapAnything Apache · 100% 官方纯图片链",
    "mapanything_official",
    f"{meta['n']:,} 点 · 官方 pred[pts3d] · 官方 1% IQR 体素",
]]
html = (
    template
    .replace("__TITLE__", "MapAnything Apache · 官方纯图片输出")
    .replace("__H1__", "MapAnything Apache — 100% 官方纯图片链")
    .replace(
        "__HINT__",
        "只输入同一组132张原图，未输入相机位姿或稀疏点；官方Apache权重、官方demo_colmap.py、"
        "官方pred[pts3d]、官方Open3D 1% IQR体素。网页只拆分XYZ/RGB用于显示，不改变坐标。"
        "拖拽旋转 · 滚轮缩放 · 右键平移。",
    )
    .replace("__NCOL__", "1")
    .replace("__PLAN__", json.dumps(plan, ensure_ascii=False))
    .replace("__META__", json.dumps({"mapanything_official": meta}))
    .replace("__REF__", json.dumps("mapanything_official"))
    .replace("__VIEW__", json.dumps(view))
    .replace("全分辨率,零降采样", "官方1% IQR体素输出")
)
(PAGE / "index.html").write_text(html)
print(f"PAGE_OK {PAGE / 'index.html'}")
