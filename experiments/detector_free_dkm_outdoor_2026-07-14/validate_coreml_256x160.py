#!/usr/bin/env python3
"""Compare a fixed-shape DKM CoreML package with its TorchScript reference."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from PIL import Image
from torchvision.transforms import InterpolationMode
from torchvision.transforms import functional as vision_functional


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--coreml", type=Path, required=True)
    parser.add_argument("--image0", type=Path, required=True)
    parser.add_argument("--image1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--compute-units",
        choices=("cpu_only", "cpu_and_gpu", "all"),
        default="cpu_and_gpu",
    )
    parser.add_argument("--flow-max-abs", type=float, default=5e-5)
    parser.add_argument("--certainty-max-abs", type=float, default=1e-3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compute_units = {
        "cpu_only": ct.ComputeUnit.CPU_ONLY,
        "cpu_and_gpu": ct.ComputeUnit.CPU_AND_GPU,
        "all": ct.ComputeUnit.ALL,
    }[args.compute_units]
    loaded = ct.models.MLModel(str(args.coreml), compute_units=compute_units)
    input_shape = tuple(loaded.get_spec().description.input[0].type.multiArrayType.shape)
    model_height, model_width = input_shape[-2:]
    image0 = tensor(args.image0, model_height, model_width)
    image1 = tensor(args.image1, model_height, model_width)
    coreml_times = []
    predictions = None
    for _ in range(3):
        started = time.perf_counter()
        predictions = loaded.predict(
            {"image0": image0.numpy(), "image1": image1.numpy()}
        )
        coreml_times.append(time.perf_counter() - started)
    assert predictions is not None

    reference = torch.jit.load(str(args.trace), map_location="cpu").eval()
    with torch.inference_mode():
        started = time.perf_counter()
        torch_outputs = reference(image0, image1)
        torch_seconds = time.perf_counter() - started
    by_shape = {
        tuple(value.shape): value.detach().float().cpu().numpy()
        for value in torch_outputs
    }
    metrics = {}
    for name, value in predictions.items():
        expected = by_shape[tuple(value.shape)]
        difference = np.abs(value - expected)
        metrics[name] = {
            "shape": list(value.shape),
            "max_abs": float(difference.max()),
            "mean_abs": float(difference.mean()),
            "p99_abs": float(np.quantile(difference, 0.99)),
        }
    flow = next(row for row in metrics.values() if row["shape"][1] == 2)
    certainty = [row for row in metrics.values() if row["shape"][1] == 1]
    passed = (
        flow["max_abs"] <= args.flow_max_abs
        and max(row["max_abs"] for row in certainty) <= args.certainty_max_abs
    )
    report = {
        "decision": "PASS_COREML_TORCH_PARITY" if passed else "FAIL_COREML_TORCH_PARITY",
        "compute_units": args.compute_units,
        "thresholds": {
            "flow_max_abs": args.flow_max_abs,
            "certainty_max_abs": args.certainty_max_abs,
        },
        "coreml_predict_seconds": coreml_times,
        "torch_cpu_predict_seconds": torch_seconds,
        "outputs": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
