from __future__ import annotations

import hashlib
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

import pycolmap

from manifest_json import dump_json


SOURCE = Path("/root/repro_official_colmap_native_20260901")
IMAGES = SOURCE / "images"
SPARSE = SOURCE / "sparse"
RUN = Path("/root/colmap_official_dense_411_20260901_v2")
WORKSPACE = RUN / "dense"
MANIFEST = RUN / "experiment.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot() -> dict:
    image_files = sorted(path for path in IMAGES.iterdir() if path.is_file())
    return {
        "contract": {
            "objective": "Official COLMAP undistort_images -> PatchMatch Stereo -> StereoFusion",
            "acceptance": [
                "132 registered input images",
                "all three official PyCOLMAP stages return without exception",
                "fused.ply exists and contains at least one vertex",
            ],
            "stop_conditions": [
                "CUDA error",
                "input model mutation",
                "missing official stage output",
            ],
        },
        "environment": {
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "pycolmap": pycolmap.__version__,
            "pycolmap_has_cuda": pycolmap.has_cuda,
            "gpu": subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader",
                ],
                text=True,
            ).strip(),
        },
        "input": {
            "image_count": len(image_files),
            "ordered_images": [path.name for path in image_files],
            "sparse_files": {
                name: {
                    "bytes": (SPARSE / name).stat().st_size,
                    "sha256": sha256(SPARSE / name),
                }
                for name in ("cameras.bin", "images.bin", "points3D.bin")
            },
        },
        "effective_defaults": {
            "undistort": pycolmap.UndistortCameraOptions().todict(),
            "patch_match": pycolmap.PatchMatchOptions().todict(),
            "stereo_fusion": pycolmap.StereoFusionOptions().todict(),
        },
        "timings_seconds": {},
        "status": "initialized",
    }


def write_manifest(data: dict) -> None:
    MANIFEST.write_text(
        dump_json(data),
        encoding="utf-8",
    )


def timed(data: dict, stage: str, function) -> None:
    print(f"STAGE_START {stage}", flush=True)
    started = time.monotonic()
    function()
    elapsed = time.monotonic() - started
    data["timings_seconds"][stage] = elapsed
    data["status"] = f"completed_{stage}"
    write_manifest(data)
    print(f"STAGE_DONE {stage} {elapsed:.3f}s", flush=True)


def main() -> None:
    if RUN.exists():
        raise RuntimeError(f"Refusing to overwrite existing run: {RUN}")
    RUN.mkdir(parents=True)
    data = snapshot()
    write_manifest(data)

    reconstruction = pycolmap.Reconstruction(SPARSE)
    if reconstruction.num_reg_images() != 132:
        raise RuntimeError(
            f"Expected 132 registered images, got {reconstruction.num_reg_images()}"
        )

    timed(
        data,
        "undistort_images",
        lambda: pycolmap.undistort_images(
            WORKSPACE,
            SPARSE,
            IMAGES,
            output_type="COLMAP",
        ),
    )
    timed(
        data,
        "patch_match_stereo",
        lambda: pycolmap.patch_match_stereo(WORKSPACE),
    )
    fused = WORKSPACE / "fused.ply"
    timed(
        data,
        "stereo_fusion",
        lambda: pycolmap.stereo_fusion(fused, WORKSPACE),
    )

    if not fused.is_file() or fused.stat().st_size == 0:
        raise RuntimeError("StereoFusion did not produce a non-empty fused.ply")
    data["output"] = {
        "path": str(fused),
        "bytes": fused.stat().st_size,
        "sha256": sha256(fused),
    }
    data["status"] = "complete"
    data["completed_unix"] = time.time()
    write_manifest(data)
    print(f"RUN_COMPLETE {fused} {fused.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
