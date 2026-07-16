#!/usr/bin/env python3
"""Evaluate CoreML/Torch DKM differences after production match filtering."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import coremltools as ct
import cv2
import numpy as np
import torch
from PIL import Image
from torch.nn import functional as torch_functional
from torchvision.transforms import InterpolationMode
from torchvision.transforms import functional as vision_functional


def load_probe(path: Path):
    spec = importlib.util.spec_from_file_location("dkm_match_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tensor(path: Path, height: int, width: int) -> torch.Tensor:
    image = Image.open(path).convert("RGB")
    image = vision_functional.resize(
        image,
        [height, width],
        interpolation=InterpolationMode.BICUBIC,
        antialias=True,
    )
    array = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
    value = vision_functional.normalize(
        torch.from_numpy(array),
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    )
    return value[None].contiguous()


def postprocess(raw: dict[tuple[int, ...], np.ndarray]):
    flow_shape = next(shape for shape in raw if len(shape) == 4 and shape[1] == 2)
    height, width = flow_shape[2:]
    certainty_shape = (2, 1, height, width)
    low_shape = next(
        shape
        for shape in raw
        if len(shape) == 4 and shape[1] == 1 and shape != certainty_shape
    )
    flow = torch.from_numpy(raw[flow_shape])
    certainty = torch.from_numpy(raw[certainty_shape])
    low_certainty = torch.from_numpy(raw[low_shape])
    low_certainty = torch_functional.interpolate(
        low_certainty,
        size=(height, width),
        align_corners=False,
        mode="bilinear",
    )
    low_certainty = 0.5 * low_certainty * (low_certainty < 0)
    certainty = (certainty - low_certainty).sigmoid()
    query_to_support = flow.permute(0, 2, 3, 1)
    wrong = (query_to_support.abs() > 1).sum(dim=-1) > 0
    certainty = certainty.masked_fill(wrong[:, None], 0)
    query_to_support = torch.clamp(query_to_support, -1, 1)
    y = torch.linspace(-1.0 + 1.0 / height, 1.0 - 1.0 / height, height)
    x = torch.linspace(-1.0 + 1.0 / width, 1.0 - 1.0 / width, width)
    grid_y, grid_x = torch.meshgrid(y, x, indexing="ij")
    query_coords = torch.stack((grid_x, grid_y), dim=-1)[None]
    query_to_support_forward, support_to_query = query_to_support.chunk(2)
    forward = torch.cat((query_coords, query_to_support_forward), dim=-1)
    reverse = torch.cat((support_to_query, query_coords), dim=-1)
    warp = torch.cat((forward, reverse), dim=2)
    certainty = torch.cat(certainty.chunk(2), dim=3)[:, 0]
    return warp[0], certainty[0]


def robust_metrics(points0: np.ndarray, points1: np.ndarray, threshold: float):
    mask = None
    if len(points0) >= 8:
        _, mask = cv2.findFundamentalMat(
            points0,
            points1,
            cv2.USAC_MAGSAC,
            threshold,
            0.999,
            10000,
        )
    inliers = int(mask.reshape(-1).astype(bool).sum()) if mask is not None else 0
    return {
        "magsac_inliers": inliers,
        "magsac_inlier_ratio": inliers / len(points0) if len(points0) else 0.0,
    }


def selected_cells(points0: np.ndarray, points1: np.ndarray, grid_px: int):
    return {
        (int(point0[0]) // grid_px, int(point0[1]) // grid_px): point1
        for point0, point1 in zip(points0, points1)
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--coreml", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--pairs", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--grid-px", type=int, default=8)
    parser.add_argument("--sampson-px", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    probe = load_probe(Path(__file__).with_name("match_cap50.py"))
    frames, image_size = probe.load_frames(args.metadata, args.images)
    torch_model = torch.jit.load(str(args.trace), map_location="cpu").eval()
    coreml_model = ct.models.MLModel(
        str(args.coreml), compute_units=ct.ComputeUnit.CPU_AND_GPU
    )
    input_shape = tuple(coreml_model.get_spec().description.input[0].type.multiArrayType.shape)
    model_height, model_width = input_shape[-2:]
    rows = []
    for pair_text in args.pairs:
        left_index, right_index = (int(value) for value in pair_text.split(":"))
        left, right = frames[left_index], frames[right_index]
        image0 = tensor(left.path, model_height, model_width)
        image1 = tensor(right.path, model_height, model_width)
        coreml_output = coreml_model.predict(
            {"image0": image0.numpy(), "image1": image1.numpy()}
        )
        with torch.inference_mode():
            torch_output = torch_model(image0, image1)
        raw_coreml = {tuple(value.shape): value for value in coreml_output.values()}
        raw_torch = {
            tuple(value.shape): value.detach().float().cpu().numpy()
            for value in torch_output
        }
        variants = {}
        for name, raw in (("coreml", raw_coreml), ("torch", raw_torch)):
            warp, certainty = postprocess(raw)
            points0, points1, scores, raw_count = probe.deterministic_grid_matches(
                warp,
                certainty,
                image_size,
                args.confidence,
                args.grid_px,
                5000,
            )
            errors = probe.sampson_error(
                probe.fundamental(left, right), points0, points1
            )
            variants[name] = {
                "points0": points0,
                "points1": points1,
                "scores": scores,
                "raw_above_confidence": raw_count,
                "selected_matches": len(points0),
                "arkit_inliers": int((errors <= args.sampson_px).sum()),
                "arkit_inlier_ratio": float((errors <= args.sampson_px).mean())
                if len(errors)
                else 0.0,
                **robust_metrics(points0, points1, args.sampson_px),
            }
        coreml_cells = selected_cells(
            variants["coreml"]["points0"], variants["coreml"]["points1"], args.grid_px
        )
        torch_cells = selected_cells(
            variants["torch"]["points0"], variants["torch"]["points1"], args.grid_px
        )
        common = sorted(coreml_cells.keys() & torch_cells.keys())
        union = coreml_cells.keys() | torch_cells.keys()
        endpoint = np.asarray(
            [np.linalg.norm(coreml_cells[cell] - torch_cells[cell]) for cell in common]
        )
        serializable = {}
        for name, values in variants.items():
            serializable[name] = {
                key: value
                for key, value in values.items()
                if key not in {"points0", "points1", "scores"}
            }
        rows.append(
            {
                "pair": [left_index, right_index],
                "variants": serializable,
                "selected_cell_intersection": len(common),
                "selected_cell_union": len(union),
                "selected_cell_jaccard": len(common) / len(union) if union else 1.0,
                "endpoint_delta_px_original": {
                    "median": float(np.median(endpoint)) if len(endpoint) else None,
                    "p90": float(np.quantile(endpoint, 0.9)) if len(endpoint) else None,
                    "max": float(endpoint.max()) if len(endpoint) else None,
                },
            }
        )
    report = {
        "decision": "DIAGNOSTIC_COREML_FILTERED_MATCH_PARITY",
        "confidence": args.confidence,
        "grid_px": args.grid_px,
        "sampson_px": args.sampson_px,
        "pairs": rows,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
