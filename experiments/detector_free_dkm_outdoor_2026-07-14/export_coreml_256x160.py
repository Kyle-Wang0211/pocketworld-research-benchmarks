#!/usr/bin/env python3
"""Export the pinned, clean DKMv3-outdoor inference closure to CoreML.

The DKM checkout must be at the pinned revision and have
``dkm_coreml_fixed_shape_cg20.patch`` applied. The wrapper deliberately exposes
only the tensors needed by the production matcher and rejects the upstream GPL
geometry helper module if it enters the process.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from PIL import Image
from torch import nn


PINNED_DKM_REVISION = "ef57565db52684e661052ba82eb361329c63af3d"
PINNED_WEIGHTS_SHA256 = (
    "fa2e6d9e3d8ee11455c0ac602bc639899df5e5d2e1809f87b1fbe4af692541b8"
)
DEFAULT_WIDTH = 256
DEFAULT_HEIGHT = 160


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_clean_utils(repo: Path, matcher_script: Path) -> None:
    spec = importlib.util.spec_from_file_location("clean_dkm_route", matcher_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load clean matcher wrapper: {matcher_script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    sys.path.insert(0, str(repo))
    module.install_clean_dkm_utils(repo)


class CoreMLMatcher(nn.Module):
    def __init__(self, matcher: nn.Module) -> None:
        super().__init__()
        self.matcher = matcher

    def forward(self, image0: torch.Tensor, image1: torch.Tensor):
        outputs = self.matcher.forward_symmetric(
            {"query": image0, "support": image1}, batched=True
        )
        return (
            outputs[1]["dense_flow"],
            outputs[1]["dense_certainty"],
            outputs[16]["dense_certainty"],
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dkm-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--image0", type=Path, required=True)
    parser.add_argument("--image1", type=Path, required=True)
    parser.add_argument("--matcher-script", type=Path, default=Path(__file__).with_name("match_cap50.py"))
    parser.add_argument("--trace-output", type=Path, required=True)
    parser.add_argument("--coreml-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(args.dkm_repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PINNED_DKM_REVISION:
        raise RuntimeError(f"DKM revision mismatch: {revision}")
    weights_hash = sha256(args.weights)
    if weights_hash != PINNED_WEIGHTS_SHA256:
        raise RuntimeError(f"weights hash mismatch: {weights_hash}")

    install_clean_utils(args.dkm_repo, args.matcher_script)
    from dkm.models.model_zoo.DKMv3 import DKMv3

    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    model = DKMv3(
        state,
        args.height,
        args.width,
        upsample_preds=False,
        device="cpu",
    ).eval()
    del state
    wrapper = CoreMLMatcher(model).eval()
    transform = sys.modules["dkm.utils"].get_tuple_transform_ops(
        (args.height, args.width), True
    )
    image0, image1 = transform(
        (
            Image.open(args.image0).convert("RGB"),
            Image.open(args.image1).convert("RGB"),
        )
    )
    inputs = (image0[None].contiguous(), image1[None].contiguous())
    traced = torch.jit.trace(wrapper, inputs, strict=False, check_trace=False)
    graph = str(traced.inlined_graph)
    forbidden = {
        "linalg_inv": graph.count("aten::linalg_inv"),
        "dynamic_int": graph.count("aten::Int"),
        "reciprocal": graph.count("aten::reciprocal"),
    }
    if any(forbidden.values()):
        raise RuntimeError(f"CoreML-forbidden traced ops remain: {forbidden}")
    if "dkm.utils.utils" in sys.modules:
        raise RuntimeError("forbidden GPL-derived dkm.utils.utils was imported")

    args.trace_output.parent.mkdir(parents=True, exist_ok=True)
    traced.save(str(args.trace_output))
    converted = ct.convert(
        traced,
        source="pytorch",
        convert_to="mlprogram",
        inputs=[
            ct.TensorType(
                name="image0",
                shape=(1, 3, args.height, args.width),
                dtype=np.float32,
            ),
            ct.TensorType(
                name="image1",
                shape=(1, 3, args.height, args.width),
                dtype=np.float32,
            ),
        ],
        minimum_deployment_target=ct.target.iOS17,
        compute_precision=ct.precision.FLOAT32,
    )
    converted.save(str(args.coreml_output))
    manifest = {
        "route": "DKMv3_outdoor_MegaDepth_only_clean_CoreML_probe",
        "production_ready": False,
        "dkm_revision": revision,
        "weights_sha256": weights_hash,
        "weights_bytes": args.weights.stat().st_size,
        "input_image_sha256": [sha256(args.image0), sha256(args.image1)],
        "resolution": [args.width, args.height],
        "cg_iterations": 20,
        "forbidden_ops": forbidden,
        "gpl_geometry_utils_imported": False,
        "torch_version": torch.__version__,
        "coremltools_version": ct.__version__,
        "trace_sha256": sha256(args.trace_output),
        "outputs": [entry.name for entry in converted.get_spec().description.output],
    }
    args.manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
