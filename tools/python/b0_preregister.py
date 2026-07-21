#!/usr/bin/env python3
"""Freeze the controlled input contract for the B0 fuseCut-vs-TSDF A/B.

This program intentionally does not create a mesh or an evaluation mask.  It
validates immutable inputs, freezes the cap100 and full413 splits, records the
single-variable experiment contract, and writes only into a caller-selected,
previously nonexistent output directory.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import importlib
import json
import os
import platform
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

import b0_input_contract as input_contract


SCHEMA_VERSION = "b0-preregistration-v1"
ROUTE_INPUT_NOT_EQUIVALENT = "ROUTE_INPUT_NOT_EQUIVALENT"
FROZEN_PROMPT_SHA256 = (
    "325855aceeee4abd46ddfaf2716f2ed9885956430eb5e2d392d25b4cc211e1a6"
)
FROZEN_CODE_HEAD = "9f8965808888f9e524cf37193de093195438b062"
FROZEN_RANDOM_SEED = 20260721
FROZEN_BOOTSTRAP_DRAWS = 10_000
FORMAL_DATASET_ID = "cap50-real-115"
FORMAL_SPLIT_ID = "cap50_93r22h_strict"
FORMAL_COORDINATE_FRAME = "optimized_sfm_cv"
FORMAL_METRES_PER_MODEL_UNIT = 1.007804831494465
FORMAL_UNIVERSE_COUNT = 115
FORMAL_RECONSTRUCTION_COUNT = 93
FORMAL_HELDOUT_COUNT = 22
FORMAL_RAW_IMAGE_SIZE_WH = (3840, 2160)
FORMAL_UNIVERSE_FRAME_ORDER_SHA256 = (
    "b632e81a048b1de96d36539e2edab67b0a721f7447d0392369cf2f96cf500c61"
)
FORMAL_RECONSTRUCTION_LIST_SHA256 = (
    "8ef00f3b310ed5d3c0ee00ff49f92e46cdfbadf703faec23e46a203367822666"
)
FORMAL_HELDOUT_LIST_SHA256 = (
    "2cf47fa3fcdb329711f762bfd360668158d3fb5915d7fd754bdfc2d6df577980"
)
FORMAL_INPUT_PRODUCER_RELATIVE_PATH = "tools/python/b0_cap50_common_cache.py"
FORMAL_INPUT_PRODUCER_OPTIONS = (
    "--metadata",
    "--sfm-meta",
    "--sfm-frames",
    "--arbitration-plan",
    "--sparse-points",
    "--image-root",
    "--model",
    "--out",
    "--dataset-id",
    "--metres-per-model-unit",
    "--compute-units",
)

# HEAD predates this experiment implementation.  These exact working-tree
# files therefore form the executable source identity; never imply that HEAD
# alone contains them.  The monitor is included even though another task owns
# its implementation, so preregistration cannot succeed before it exists.
FROZEN_CODE_RELATIVE_PATHS = (
    FORMAL_INPUT_PRODUCER_RELATIVE_PATH,
    "tools/python/b0_input_contract.py",
    "tools/python/b0_preregister.py",
    "tools/python/b0_export_alicevision.py",
    "tools/python/b0_prepare_eval.py",
    "tools/python/b0_run_monitored.py",
    "tools/python/mesh_ab_eval.py",
    "tools/python/pw_mesh_bench.py",
    "tools/python/pw_tsdf_trio.py",
)

MONITOR_RESOURCE_LIMITS = {
    "disk_path": "/",
    "start_available_gib_min": 15.0,
    "running_stop_below_available_gib": 6.0,
    "sample_interval_seconds": 1800,
    "peak_rss_gib_max": 12.0,
    "swap_growth_gib_max": 4.0,
    "wall_time_seconds_max": 14400,
}

FROZEN_ENVIRONMENT_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "MKL_NUM_THREADS",
    "PYTHONHASHSEED",
    "PATH",
    "DYLD_LIBRARY_PATH",
    "TMPDIR",
)

REQUIRED_PYTHON_MODULES = ("OpenEXR", "cv2", "open3d", "numpy")

EXPECTED_DMCACHE_SHA256 = (
    "9eeff8cd3e899ce000dea4fdf33a0e8b91c1819e604daa75f91a53f1dfdeba38"
)
EXPECTED_DMCACHE_SIGNATURE = (
    "g3_p0.5_bnd0.03_nrm0.5_pcNone_pcn1_fsNone_fst0.02_reNone_er0"
)
EXPECTED_DEPTH_SHAPE = (413, 512, 896)
EXPECTED_MODEL_CACHE_SHA256 = (
    "7b569a5f5d87028edca9067132cc30a76f14e4950d7d9985410b2c4575954413"
)
EXPECTED_TRIO_REFS_SHA256 = (
    "cd1166adba7a0c47c90c056134aa74e6801f455946f0b414d28f2c9b55baf7b6"
)
EXPECTED_CAP_LIST_SHA256 = (
    "8f8a3f8ea400c827d4bad9289f898f47a8fac21922d0c3ccd5ddf4a23201cf5f"
)
EXPECTED_SPATIAL_MANIFEST_SHA256 = (
    "a0d96d9c7ba0ffa78329345573e52be789e08f79ecd61f21bfd48fd76ba1f350"
)
SPATIAL_MANIFEST_REPOSITORY_PATH = (
    "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/"
    "external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json"
)

EXPECTED_CAP_HELDOUT_SHA256 = (
    "e528e090fc3af9307cb3565c6b97f5f6cefec629595ab3b1cdb11067d98e43a0"
)
EXPECTED_CAP_RECONSTRUCTION_SHA256 = (
    "6450617b85f40e37104bee07e943ebfdfbc76ee104ab07d796893d14953226f1"
)
EXPECTED_FULL_HELDOUT_SHA256 = (
    "5e16f68e603af0b3e27b6957ba0dad0fc0fbeec1d068a04e0b22a2ed78696805"
)
EXPECTED_FULL_RECONSTRUCTION_SHA256 = (
    "d2dca3eac2f8efbf18b1efdd9e08b0a6e9b504eb71af378b4444bff035e54a41"
)
EXPECTED_FULL_ALL_SHA256 = (
    "80426c1d4b1315a28dd2c2de750cfa6982f80496ff7425c76ae6fa526bd51717"
)

CAP_FRAME_COUNT = 100
CAP_HELDOUT_INDICES = tuple(range(4, 95, 5))
FULL_FRAME_COUNT = 413
FULL_HELDOUT_INDICES = tuple(range(4, FULL_FRAME_COUNT, 5))
SPATIAL_FRAME_COUNT = 414
UNREGISTERED_SPATIAL_FRAME = "cell_92_slot_8.jpg"

FROZEN_SIM3 = {
    "scale": 0.21677133346045502,
    "rotation_row_major": [
        [-0.5164642748270721, -0.40075508246013364, 0.7567430321514155],
        [-0.8145289003158794, -0.04275669459765485, -0.5785451889155140],
        [0.2642107556053517, -0.9151869912479386, -0.3043442913428719],
    ],
    "translation": [
        2.0492393928665282,
        -0.19619993852968876,
        1.5497805581256314,
    ],
    "canonical_encoding": "<f8 [scale,R row-major,t]",
    "canonical_sha256": (
        "ca5e4b72dcb4e6a7bee8af8182c2947e006de5a59e8ca7c1e030ffee288b70f4"
    ),
}


class PreRegistrationError(ValueError):
    """Raised when an input cannot satisfy the frozen B0 contract."""


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while True:
            block = stream.read(chunk_size)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _frame_list_bytes(names: Sequence[str]) -> bytes:
    return ("\n".join(names) + "\n").encode("utf-8")


def hash_frame_list(names: Sequence[str]) -> str:
    return hashlib.sha256(_frame_list_bytes(names)).hexdigest()


def _validate_names(names: Sequence[object], *, expected_count: int, label: str) -> list[str]:
    if len(names) != expected_count:
        raise PreRegistrationError(
            f"{label}: expected {expected_count} frames, found {len(names)}"
        )
    result: list[str] = []
    seen: set[str] = set()
    for value in names:
        if not isinstance(value, str):
            raise PreRegistrationError(f"{label}: non-string frame name")
        if (
            not value
                or value != value.strip()
                or "\x00" in value
                or "/" in value
                or "\\" in value
                or Path(value).name != value
            or value in {".", ".."}
            or value in seen
        ):
            raise PreRegistrationError(f"{label}: invalid or duplicate frame name {value!r}")
        seen.add(value)
        result.append(value)
    return result


def read_cap_list(path: Path | str) -> tuple[list[str], bytes]:
    source = Path(path)
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PreRegistrationError(f"cap list is not readable UTF-8: {source}") from exc
    # The file itself is a frozen artifact.  Comments and blank lines are not
    # normalized away because that would make the content hash misleading.
    lines = text.splitlines()
    names = _validate_names(lines, expected_count=CAP_FRAME_COUNT, label="cap list")
    if raw != _frame_list_bytes(names):
        raise PreRegistrationError(
            "cap list must be canonical UTF-8, one basename per line, with final newline"
        )
    return names, raw


def split_cap100(cap_frames: Sequence[str]) -> tuple[list[str], list[str]]:
    frames = _validate_names(
        list(cap_frames), expected_count=CAP_FRAME_COUNT, label="cap100"
    )
    heldout_indices = set(CAP_HELDOUT_INDICES)
    heldout = [name for index, name in enumerate(frames) if index in heldout_indices]
    reconstruction = [
        name for index, name in enumerate(frames) if index not in heldout_indices
    ]
    if len(heldout) != 19 or len(reconstruction) != 81:
        raise AssertionError("frozen cap100 split count changed")
    return reconstruction, heldout


def split_full413(all_frames: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return the historical deterministic full-quality split.

    The 413-name dmcache order is authoritative.  Every fifth global slot,
    starting at index 4 and ending at index 409, is withheld from fusion.  The
    full-quality split is intentionally independent of the spatial cap100
    order; both result lists retain dmcache order.
    """
    full = _validate_names(
        list(all_frames), expected_count=FULL_FRAME_COUNT, label="full413"
    )
    heldout_indices = set(FULL_HELDOUT_INDICES)
    heldout = [name for index, name in enumerate(full) if index in heldout_indices]
    reconstruction = [
        name for index, name in enumerate(full) if index not in heldout_indices
    ]
    if (len(reconstruction), len(heldout)) != (331, 82):
        raise AssertionError("frozen full413 split count changed")
    return reconstruction, heldout


def _load_spatial_manifest(
    path: Path | str,
) -> tuple[list[str], list[str], str]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreRegistrationError(f"invalid spatial manifest: {source}") from exc
    if not isinstance(payload, dict):
        raise PreRegistrationError("spatial manifest root must be an object")
    frames = payload.get("frames")
    order = payload.get("spatialOrder")
    if (
        not isinstance(frames, list)
        or not isinstance(order, list)
        or len(frames) != SPATIAL_FRAME_COUNT
        or len(order) != SPATIAL_FRAME_COUNT
    ):
        raise PreRegistrationError(
            "spatial manifest must contain exactly 414 frames and 414 order entries"
        )
    normalized_order: list[int] = []
    manifest_names: list[str] = []
    for entry in frames:
        if not isinstance(entry, dict) or not isinstance(entry.get("jpegPath"), str):
            raise PreRegistrationError("spatial manifest frame lacks jpegPath")
        manifest_names.append(Path(entry["jpegPath"]).name)
    _validate_names(
        manifest_names,
        expected_count=SPATIAL_FRAME_COUNT,
        label="spatial manifest frames",
    )
    for raw_index in order:
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            raise PreRegistrationError("spatialOrder contains a non-integer index")
        if raw_index < 0 or raw_index >= len(frames):
            raise PreRegistrationError("spatialOrder index is out of bounds")
        normalized_order.append(raw_index)
    if len(set(normalized_order)) != SPATIAL_FRAME_COUNT:
        raise PreRegistrationError("spatialOrder must be a permutation of 0..413")
    derived = [manifest_names[index] for index in normalized_order[:CAP_FRAME_COUNT]]
    names = _validate_names(derived, expected_count=100, label="derived cap100")
    schema = payload.get("schemaVersion")
    return names, manifest_names, schema if isinstance(schema, str) else "UNSPECIFIED"


def derive_cap100_from_spatial_manifest(path: Path | str) -> tuple[list[str], str]:
    names, _, schema = _load_spatial_manifest(path)
    return names, schema


def _assert_hash(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise PreRegistrationError(
            f"{label} SHA-256 mismatch: expected {expected}, found {actual}"
        )


def _require_absolute_file(path: Path | str, *, label: str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute():
        raise PreRegistrationError(f"{label} must be an absolute path: {supplied}")
    resolved = supplied.resolve()
    if not resolved.is_file():
        raise PreRegistrationError(f"{label} is not a regular file: {resolved}")
    return resolved


def _canonical_json_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_absolute_directory(path: Path | str, *, label: str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute():
        raise PreRegistrationError(f"{label} must be an absolute path: {supplied}")
    resolved = supplied.resolve()
    if not resolved.is_dir():
        raise PreRegistrationError(f"{label} is not a directory: {resolved}")
    return resolved


@lru_cache(maxsize=1)
def _probe_required_python_modules() -> dict[str, dict[str, Any]]:
    probes: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_PYTHON_MODULES:
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            probes[name] = {
                "importable": False,
                "version": None,
                "module_file": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        module_file_value = getattr(module, "__file__", None)
        module_file = (
            Path(module_file_value).resolve()
            if isinstance(module_file_value, str)
            else None
        )
        probes[name] = {
            "importable": True,
            "version": str(getattr(module, "__version__", "unknown")),
            "module_file": None if module_file is None else str(module_file),
            "module_file_sha256": (
                sha256_file(module_file)
                if module_file is not None and module_file.is_file()
                else None
            ),
            "error": None,
        }
    probes["OpenEXR"]["required_capability"] = "OpenEXR.File typed metadata writer"
    probes["OpenEXR"]["capability_present"] = bool(
        probes["OpenEXR"]["importable"]
        and hasattr(importlib.import_module("OpenEXR"), "File")
    )
    probes["cv2"]["required_capability"] = "serialized EXR read-back"
    probes["open3d"]["required_capability"] = "tensor ray casting"
    return probes


def _freeze_execution_identity(
    *, code_root: Path | str, alicevision_binary: Path | str
) -> dict[str, Any]:
    """Hash executable dirty sources, the native binary, and this environment.

    The experiment implementation is intentionally identified independently
    from ``FROZEN_CODE_HEAD`` because most B0 scripts are dirty or untracked in
    the isolated worktree.  A missing script is a hard preregistration failure,
    including the separately implemented resource monitor.
    """

    root = _require_absolute_directory(code_root, label="code_root")
    code_files: list[dict[str, Any]] = []
    for relative_path in FROZEN_CODE_RELATIVE_PATHS:
        source = root / relative_path
        if not source.is_file():
            raise PreRegistrationError(
                f"dirty code bundle is incomplete; missing {relative_path} under {root}"
            )
        code_files.append(
            {
                "relative_path": relative_path,
                "absolute_path": str(source.resolve()),
                "sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
            }
        )
    code_bundle_payload = {
        "git_head": FROZEN_CODE_HEAD,
        "git_head_contains_experiment_code": False,
        "files": code_files,
    }

    binary = _require_absolute_file(
        alicevision_binary, label="alicevision meshing binary"
    )
    if not os.access(binary, os.X_OK):
        raise PreRegistrationError(
            f"alicevision meshing binary is not executable: {binary}"
        )

    python_executable = Path(sys.executable).resolve()
    python_identity: dict[str, Any] = {
        "executable": str(python_executable),
        "version": sys.version,
        "implementation": platform.python_implementation(),
        "numpy_version": np.__version__,
    }
    if python_executable.is_file():
        python_identity["executable_sha256"] = sha256_file(python_executable)
    else:
        python_identity["executable_sha256"] = None
    module_probes = _probe_required_python_modules()
    if any(not probe["importable"] for probe in module_probes.values()) or not module_probes[
        "OpenEXR"
    ]["capability_present"]:
        raise PreRegistrationError(
            "formal B0 Python environment lacks OpenEXR/cv2/open3d/numpy capability"
        )
    environment_identity = {
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "python": python_identity,
        "required_python_modules": module_probes,
        "selected_process_environment": {
            name: os.environ.get(name) for name in FROZEN_ENVIRONMENT_VARIABLES
        },
        "dependency_lock": {
            "status": "ABSENT",
            "path": None,
            "sha256": None,
            "note": "no repository-local uv.lock exists at this frozen code root",
        },
    }
    lockfile = root / "uv.lock"
    if lockfile.is_file():
        environment_identity["dependency_lock"] = {
            "status": "PRESENT",
            "path": str(lockfile.resolve()),
            "sha256": sha256_file(lockfile),
        }

    return {
        "source_state": {
            "git_head": FROZEN_CODE_HEAD,
            "git_head_contains_experiment_code": False,
            "statement": (
                "Git HEAD is only the base revision; the executable experiment "
                "identity is the separately hashed dirty/untracked code bundle."
            ),
            "dirty_code_bundle": {
                **code_bundle_payload,
                "bundle_sha256": _canonical_json_sha256(code_bundle_payload),
            },
        },
        "alicevision_binary": {
            "path": str(binary),
            "sha256": sha256_file(binary),
            "size_bytes": binary.stat().st_size,
            "executable": True,
        },
        "environment_identity": {
            "sha256": _canonical_json_sha256(environment_identity),
            "identity": environment_identity,
            "verification_rule": (
                "the resource wrapper must capture the route environment and it "
                "must match this preregistered identity for both arms"
            ),
        },
    }


def _monitor_prefix(
    *,
    label: str,
    run_leaf: str,
    python_executable: str = "python3.11",
    preregistered_contract: str | None = None,
    phase: str | None = None,
    attest_files: Sequence[str] = (),
    attest_trees: Sequence[str] = (),
    require_prior_statuses: Sequence[str] = (),
) -> list[str]:
    prefix = [
        python_executable,
        "tools/python/b0_run_monitored.py",
        "--label",
        label,
        "--resource-log",
        f"{run_leaf}/resources.ndjson",
        "--status",
        f"{run_leaf}/status.json",
        "--disk-path",
        str(MONITOR_RESOURCE_LIMITS["disk_path"]),
        "--start-available-gib",
        str(int(MONITOR_RESOURCE_LIMITS["start_available_gib_min"])),
        "--stop-available-gib",
        str(int(MONITOR_RESOURCE_LIMITS["running_stop_below_available_gib"])),
        "--sample-interval-seconds",
        str(MONITOR_RESOURCE_LIMITS["sample_interval_seconds"]),
        "--resource-poll-seconds",
        "1",
        "--peak-rss-gib",
        str(int(MONITOR_RESOURCE_LIMITS["peak_rss_gib_max"])),
        "--swap-growth-gib",
        str(int(MONITOR_RESOURCE_LIMITS["swap_growth_gib_max"])),
        "--wall-time-seconds",
        str(MONITOR_RESOURCE_LIMITS["wall_time_seconds_max"]),
    ]
    if (preregistered_contract is None) != (phase is None):
        raise ValueError(
            "preregistered_contract and phase must be supplied together"
        )
    if preregistered_contract is not None:
        prefix.extend(
            [
                "--preregistered-contract",
                preregistered_contract,
                "--phase",
                phase,
            ]
        )
    for path in attest_files:
        prefix.extend(["--attest-file", path])
    for path in attest_trees:
        prefix.extend(["--attest-tree", path])
    for path in require_prior_statuses:
        prefix.extend(["--require-prior-status", path])
    prefix.append("--")
    return prefix


def _load_trio_refs(path: Path) -> tuple[list[str], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreRegistrationError(f"invalid trio_refs JSON: {path}") from exc
    if not isinstance(payload, dict) or set(payload) != {"pool", "refs"}:
        raise PreRegistrationError("trio_refs root must contain exactly pool and refs")
    if not isinstance(payload["pool"], list) or not isinstance(payload["refs"], list):
        raise PreRegistrationError("trio_refs pool and refs must be arrays")
    pool = _validate_names(
        payload["pool"], expected_count=FULL_FRAME_COUNT, label="trio_refs pool"
    )
    refs = _validate_names(
        payload["refs"], expected_count=FULL_FRAME_COUNT, label="trio_refs refs"
    )
    return pool, refs


def _load_dmcache(path: Path) -> tuple[list[str], np.ndarray, str]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {"frames", "dm", "sig"}
            if not required.issubset(archive.files):
                raise PreRegistrationError(
                    f"dmcache lacks required arrays: {sorted(required - set(archive.files))}"
                )
            frames_raw = archive["frames"].tolist()
            depth = np.asarray(archive["dm"])
            signature_raw = archive["sig"]
            if signature_raw.shape != ():
                raise PreRegistrationError("dmcache signature must be scalar")
            signature = str(signature_raw.item())
    except PreRegistrationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise PreRegistrationError(f"invalid dmcache: {path}") from exc
    frames = _validate_names(
        frames_raw, expected_count=FULL_FRAME_COUNT, label="dmcache frames"
    )
    if depth.shape != EXPECTED_DEPTH_SHAPE or depth.dtype != np.dtype(np.float32):
        raise PreRegistrationError(
            "dmcache depth contract mismatch: "
            f"expected {EXPECTED_DEPTH_SHAPE} float32, found {depth.shape} {depth.dtype}"
        )
    if signature != EXPECTED_DMCACHE_SIGNATURE:
        raise PreRegistrationError(
            "dmcache signature mismatch: "
            f"expected {EXPECTED_DMCACHE_SIGNATURE!r}, found {signature!r}"
        )
    return frames, depth, signature


def _load_model_cache(
    path: Path,
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, dict[str, dict[str, Any]]]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {"names", "K", "w2c", "centers", "obs_idx", "obs_off", "pts"}
            if not required.issubset(archive.files):
                raise PreRegistrationError(
                    "model cache lacks required arrays: "
                    f"{sorted(required - set(archive.files))}"
                )
            names_raw = archive["names"].tolist()
            intrinsics = np.asarray(archive["K"])
            world_to_camera = np.asarray(archive["w2c"])
            centers = np.asarray(archive["centers"])
            obs_idx = np.asarray(archive["obs_idx"])
            obs_off = np.asarray(archive["obs_off"])
            points = np.asarray(archive["pts"])
    except PreRegistrationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise PreRegistrationError(f"invalid model cache: {path}") from exc
    names = _validate_names(
        names_raw, expected_count=FULL_FRAME_COUNT, label="model cache names"
    )
    if intrinsics.shape != (413, 3, 3) or intrinsics.dtype != np.dtype(np.float32):
        raise PreRegistrationError(
            f"model K contract mismatch: found {intrinsics.shape} {intrinsics.dtype}"
        )
    if world_to_camera.shape != (413, 4, 4) or world_to_camera.dtype != np.dtype(
        np.float32
    ):
        raise PreRegistrationError(
            "model w2c contract mismatch: "
            f"found {world_to_camera.shape} {world_to_camera.dtype}"
        )
    if centers.shape != (413, 3) or centers.dtype != np.dtype(np.float64):
        raise PreRegistrationError(
            f"model centers contract mismatch: found {centers.shape} {centers.dtype}"
        )
    if obs_idx.ndim != 1 or obs_idx.dtype != np.dtype(np.int64):
        raise PreRegistrationError(
            f"model obs_idx contract mismatch: found {obs_idx.shape} {obs_idx.dtype}"
        )
    if obs_off.shape != (414,) or obs_off.dtype != np.dtype(np.int64):
        raise PreRegistrationError(
            f"model obs_off contract mismatch: found {obs_off.shape} {obs_off.dtype}"
        )
    if points.ndim != 2 or points.shape[1:] != (3,) or points.dtype != np.dtype(
        np.float64
    ):
        raise PreRegistrationError(
            f"model pts contract mismatch: found {points.shape} {points.dtype}"
        )
    if (
        obs_off[0] != 0
        or obs_off[-1] != len(obs_idx)
        or np.any(obs_off[1:] < obs_off[:-1])
        or (
            obs_idx.size
            and (int(obs_idx.min()) < 0 or int(obs_idx.max()) >= len(points))
        )
    ):
        raise PreRegistrationError("model observation index contract mismatch")
    if not all(
        np.isfinite(values).all()
        for values in (intrinsics, world_to_camera, centers, points)
    ):
        raise PreRegistrationError("model camera/point arrays contain non-finite values")
    if np.any(intrinsics[:, 0, 0] <= 0) or np.any(intrinsics[:, 1, 1] <= 0):
        raise PreRegistrationError("model K contains a non-positive focal length")
    arrays = {
        "names": {"shape": [413], "dtype": str(np.asarray(names).dtype)},
        "K": {"shape": list(intrinsics.shape), "dtype": str(intrinsics.dtype)},
        "w2c": {
            "shape": list(world_to_camera.shape),
            "dtype": str(world_to_camera.dtype),
        },
        "centers": {"shape": list(centers.shape), "dtype": str(centers.dtype)},
        "obs_idx": {"shape": list(obs_idx.shape), "dtype": str(obs_idx.dtype)},
        "obs_off": {"shape": list(obs_off.shape), "dtype": str(obs_off.dtype)},
        "pts": {"shape": list(points.shape), "dtype": str(points.dtype)},
    }
    return names, intrinsics, world_to_camera, centers, arrays


def _describe_list(relative_path: str, names: Sequence[str]) -> dict[str, Any]:
    return {
        "file": relative_path,
        "count": len(names),
        "sha256": hash_frame_list(names),
    }


def _semantic_inputs(
    all_frames: Sequence[str],
    depth: np.ndarray,
    model_names: Sequence[str],
    intrinsics: np.ndarray,
    world_to_camera: np.ndarray,
    cap_reconstruction: Sequence[str],
    cap_heldout: Sequence[str],
    full_reconstruction: Sequence[str],
    full_heldout: Sequence[str],
) -> dict[str, Any]:
    model_index = {name: index for index, name in enumerate(model_names)}
    per_frame: list[dict[str, Any]] = []
    by_name: dict[str, str] = {}
    for dm_index, name in enumerate(all_frames):
        mi = model_index[name]
        frame_depth = depth[dm_index]
        mask = np.isfinite(frame_depth) & (frame_depth > 0)
        semantic_hash = input_contract.canonical_frame_semantic_sha256(
            name,
            mask,
            frame_depth,
            intrinsics[mi],
            world_to_camera[mi],
        )
        per_frame.append(
            {
                "name": name,
                "dmcache_index": dm_index,
                "model_cache_index": mi,
                "sha256": semantic_hash,
            }
        )
        by_name[name] = semantic_hash

    def subset_hash(names: Sequence[str]) -> str:
        return input_contract.semantic_manifest_sha256(by_name[name] for name in names)

    return {
        "hash_version": input_contract.SEMANTIC_HASH_VERSION,
        "definition": [
            "exact frame basename",
            "mask = isfinite(camera_Z_depth) and camera_Z_depth > 0",
            "camera-Z depth bytes without conversion",
            "matched K bytes",
            "matched world-to-camera bytes in LAPA model frame",
        ],
        "all413_manifest_sha256": subset_hash(all_frames),
        "cap100_reconstruction_manifest_sha256": subset_hash(cap_reconstruction),
        "cap100_heldout_manifest_sha256": subset_hash(cap_heldout),
        "full413_reconstruction_manifest_sha256": subset_hash(full_reconstruction),
        "full413_heldout_manifest_sha256": subset_hash(full_heldout),
        "per_frame": per_frame,
    }


@dataclass(frozen=True)
class _PreflightBundle:
    dmcache_path: Path
    model_path: Path
    trio_refs_path: Path
    spatial_manifest_path: Path
    cap100_list_path: Path
    file_hashes: dict[str, str]
    cap_raw: bytes
    all_frames: list[str]
    depth: np.ndarray
    signature: str
    model_names: list[str]
    intrinsics: np.ndarray
    world_to_camera: np.ndarray
    centers: np.ndarray
    model_arrays: dict[str, dict[str, Any]]
    trio_pool: list[str]
    trio_refs: list[str]
    spatial_schema: str
    spatial_names: list[str]
    cap_frames: list[str]
    cap_reconstruction: list[str]
    cap_heldout: list[str]
    full_reconstruction: list[str]
    full_heldout: list[str]
    list_hashes: dict[str, str]
    semantic: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            "status": "FROZEN_INPUTS_VERIFIED",
            "read_only": True,
            "counts": {
                "cap100_all": len(self.cap_frames),
                "cap100_reconstruction": len(self.cap_reconstruction),
                "cap100_heldout": len(self.cap_heldout),
                "full413_all": len(self.all_frames),
                "full413_reconstruction": len(self.full_reconstruction),
                "full413_heldout": len(self.full_heldout),
            },
            "hashes": {**self.file_hashes, **self.list_hashes},
            "dmcache": {
                "shape": list(self.depth.shape),
                "dtype": str(self.depth.dtype),
                "signature": self.signature,
            },
            "trio_model_lapa": {"arrays": self.model_arrays},
            "trio_refs": {"pool_count": len(self.trio_pool), "refs_count": len(self.trio_refs)},
            "spatial_manifest": {
                "schema_version": self.spatial_schema,
                "frame_count": len(self.spatial_names),
            },
        }


@dataclass(frozen=True)
class _GenericInputBundle:
    input_contract_path: Path
    input_contract_raw: bytes
    input_contract_sha256: str
    payload: Mapping[str, Any]
    dataset_id: str
    split_id: str
    coordinate_frame: str
    metres_per_model_unit: float
    dmcache_path: Path
    model_cache_path: Path
    image_root: Path
    universe: list[str]
    reconstruction: list[str]
    heldout: list[str]
    dmcache_sha256: str
    model_cache_sha256: str
    image_manifest_sha256: str
    reconstruction_list_sha256: str
    heldout_list_sha256: str
    dmcache_signature: str
    depth_shape: list[int]
    reconstruction_total_raster_pixels: int
    reconstruction_valid_depth_points: int


@dataclass(frozen=True)
class _InputProducerMonitorEvidence:
    status_path: Path
    status_sha256: str
    status_size_bytes: int
    child_argv: list[str]
    child_argv_sha256: str
    attestation_bundle_sha256: str
    provenance_path: Path
    provenance_sha256: str
    provenance_size_bytes: int
    output_tree: Mapping[str, Any] | None


def _generic_not_equivalent() -> None:
    raise PreRegistrationError(ROUTE_INPUT_NOT_EQUIVALENT)


def _canonical_regular_file_identity(
    path: Path | str, *, label: str
) -> tuple[Path, int, str]:
    supplied = Path(path)
    if not supplied.is_absolute() or supplied.is_symlink():
        raise PreRegistrationError(f"{label} must be an absolute nonsymlink file")
    resolved = supplied.resolve(strict=False)
    if resolved != supplied or not supplied.is_file():
        raise PreRegistrationError(f"{label} must be a canonical regular file")
    before = supplied.stat()
    digest = sha256_file(supplied)
    after = supplied.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise PreRegistrationError(f"{label} changed while being hashed")
    return supplied, after.st_size, digest


def _current_tree_attestation(path: Path | str) -> dict[str, Any]:
    root = Path(path)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.resolve(strict=False) != root
    ):
        raise PreRegistrationError(
            "input producer output tree must be absolute, canonical, and nonsymlink"
        )
    try:
        root_mode = root.lstat().st_mode
    except OSError as exc:
        raise PreRegistrationError(
            f"input producer output tree is missing: {root}"
        ) from exc
    if not stat.S_ISDIR(root_mode):
        raise PreRegistrationError(
            f"input producer output tree is not a directory: {root}"
        )

    files: list[tuple[str, Path]] = []
    directory_identities: dict[str, tuple[int, int, int]] = {}
    for current_value, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_value)
        current_stat = current.lstat()
        relative_directory = current.relative_to(root).as_posix()
        if current.is_symlink() or not stat.S_ISDIR(current_stat.st_mode):
            raise PreRegistrationError(
                f"input producer output tree contains a non-directory: {current}"
            )
        directory_identities[relative_directory] = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_mtime_ns,
        )
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISDIR(child_stat.st_mode):
                raise PreRegistrationError(
                    f"input producer output tree contains a symlink or special directory: {child}"
                )
        for name in file_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISREG(child_stat.st_mode):
                raise PreRegistrationError(
                    f"input producer output tree contains a symlink or special file: {child}"
                )
            files.append((child.relative_to(root).as_posix(), child))
    files.sort(key=lambda item: item[0])

    file_records: list[dict[str, Any]] = []
    total_size = 0
    for relative, child in files:
        _, size, digest = _canonical_regular_file_identity(
            child, label=f"input producer output tree file {relative}"
        )
        total_size += size
        file_records.append(
            {
                "relative_path": relative,
                "size_bytes": size,
                "sha256": digest,
            }
        )

    after_directories: dict[str, tuple[int, int, int]] = {}
    after_files: list[str] = []
    for current_value, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_value)
        current_stat = current.lstat()
        relative_directory = current.relative_to(root).as_posix()
        if current.is_symlink() or not stat.S_ISDIR(current_stat.st_mode):
            raise PreRegistrationError("input producer output tree changed while hashed")
        after_directories[relative_directory] = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_mtime_ns,
        )
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISDIR(child_stat.st_mode):
                raise PreRegistrationError(
                    "input producer output tree changed while hashed"
                )
        for name in file_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISREG(child_stat.st_mode):
                raise PreRegistrationError(
                    "input producer output tree changed while hashed"
                )
            after_files.append(child.relative_to(root).as_posix())
    after_files.sort()
    if (
        directory_identities != after_directories
        or [relative for relative, _ in files] != after_files
    ):
        raise PreRegistrationError("input producer output tree changed while hashed")
    tree_payload = {"files": file_records}
    return {
        "schema_version": "b0-attested-tree-v1",
        "path": str(root),
        "file_count": len(file_records),
        "total_size_bytes": total_size,
        "files": file_records,
        "tree_sha256": _canonical_json_sha256(tree_payload),
    }


def _parse_formal_input_producer_command(
    argv: object,
    *,
    bundle: _GenericInputBundle,
    code_root: Path,
    execution_identity: Mapping[str, Any],
) -> tuple[list[str], dict[str, str]]:
    if (
        not isinstance(argv, list)
        or len(argv) < 3
        or any(not isinstance(item, str) or not item or "\x00" in item for item in argv)
        or any("<" in item or ">" in item for item in argv)
    ):
        _generic_not_equivalent()
    command = list(argv)
    frozen_python = Path(
        execution_identity["environment_identity"]["identity"]["python"][
            "executable"
        ]
    )
    try:
        command_python = Path(command[0])
        command_script = Path(command[1])
        if (
            not command_python.is_absolute()
            or command_python.resolve() != frozen_python.resolve()
            or not command_script.is_absolute()
            or command_script.resolve()
            != (code_root / FORMAL_INPUT_PRODUCER_RELATIVE_PATH).resolve()
        ):
            _generic_not_equivalent()
    except (OSError, RuntimeError):
        _generic_not_equivalent()

    raw_options = command[2:]
    if len(raw_options) != 2 * len(FORMAL_INPUT_PRODUCER_OPTIONS):
        _generic_not_equivalent()
    parsed: dict[str, str] = {}
    for index in range(0, len(raw_options), 2):
        option, value = raw_options[index : index + 2]
        if (
            option not in FORMAL_INPUT_PRODUCER_OPTIONS
            or option in parsed
            or value.startswith("--")
        ):
            _generic_not_equivalent()
        parsed[option] = value
    if set(parsed) != set(FORMAL_INPUT_PRODUCER_OPTIONS):
        _generic_not_equivalent()
    if (
        parsed["--dataset-id"] != FORMAL_DATASET_ID
        or not _exact_float(
            parsed["--metres-per-model-unit"], FORMAL_METRES_PER_MODEL_UNIT
        )
        or parsed["--compute-units"] not in {"cpu_and_gpu", "cpu_only"}
    ):
        _generic_not_equivalent()

    file_options = (
        "--metadata",
        "--sfm-meta",
        "--sfm-frames",
        "--arbitration-plan",
        "--sparse-points",
    )
    try:
        for option in file_options:
            _require_absolute_file(parsed[option], label=f"producer {option}")
        producer_image_root = _require_absolute_directory(
            parsed["--image-root"], label="producer --image-root"
        )
        _require_absolute_directory(parsed["--model"], label="producer --model")
    except PreRegistrationError:
        _generic_not_equivalent()
    producer_out = Path(parsed["--out"])
    if (
        not producer_out.is_absolute()
        or producer_out.resolve() != producer_out
        or producer_out != bundle.input_contract_path.parent
        or producer_image_root != bundle.image_root
    ):
        _generic_not_equivalent()
    return command, parsed


def _load_input_producer_monitor_evidence(
    *,
    status_path: Path | str,
    bundle: _GenericInputBundle,
    code_root: Path,
    execution_identity: Mapping[str, Any],
) -> _InputProducerMonitorEvidence:
    """Prove the accepted input cache came from one monitored full-115 run."""

    try:
        status, status_size, status_sha = _canonical_regular_file_identity(
            status_path, label="input producer monitor status"
        )
        payload = json.loads(status.read_text(encoding="utf-8"))
    except (PreRegistrationError, OSError, UnicodeError, json.JSONDecodeError):
        _generic_not_equivalent()
    if not isinstance(payload, Mapping):
        _generic_not_equivalent()
    command_record = payload.get("command")
    if not isinstance(command_record, Mapping):
        _generic_not_equivalent()
    child_argv, _ = _parse_formal_input_producer_command(
        command_record.get("argv"),
        bundle=bundle,
        code_root=code_root,
        execution_identity=execution_identity,
    )
    child_sha = _canonical_json_sha256(child_argv)
    if (
        payload.get("schema_version") != "b0-monitored-command-v1"
        or payload.get("verdict") != "PASS"
        or payload.get("command_outcome") != "SUCCESS"
        or payload.get("started") is not True
        or payload.get("exit_code") != 0
        or payload.get("launch_error") is not None
        or command_record.get("shell") is not False
        or command_record.get("canonical_sha256") != child_sha
    ):
        _generic_not_equivalent()

    provenance_path = bundle.input_contract_path.parent / "provenance.json"
    try:
        provenance, provenance_size, provenance_sha = (
            _canonical_regular_file_identity(
                provenance_path, label="input producer provenance"
            )
        )
        provenance_payload = json.loads(provenance.read_text(encoding="utf-8"))
    except (PreRegistrationError, OSError, UnicodeError, json.JSONDecodeError):
        _generic_not_equivalent()
    if not isinstance(provenance_payload, Mapping):
        _generic_not_equivalent()
    generator = provenance_payload.get("generator")
    final_contract = provenance_payload.get("final_input_contract")
    provenance_dmcache = provenance_payload.get("dmcache")
    provenance_model = provenance_payload.get("model_cache")
    producer_script = (code_root / FORMAL_INPUT_PRODUCER_RELATIVE_PATH).resolve()
    if (
        provenance_payload.get("schema_version")
        != "b0-cap50-common-cache-provenance-v1"
        or provenance_payload.get("status") != "complete"
        or provenance_payload.get("dry_contract") is not False
        or provenance_payload.get("publishable_as_full") is not True
        or provenance_payload.get("run_mode") != "full_common_cache"
        or provenance_payload.get("requested_limit") is not None
        or not isinstance(generator, Mapping)
        or generator.get("script") != str(producer_script)
        or generator.get("script_sha256") != sha256_file(producer_script)
        or not isinstance(final_contract, Mapping)
        or final_contract.get("path") != str(bundle.input_contract_path)
        or final_contract.get("sha256") != bundle.input_contract_sha256
        or final_contract.get("schema_version")
        != input_contract.INPUT_CONTRACT_SCHEMA_VERSION
        or final_contract.get("prewrite_validated") is not True
        or final_contract.get("postwrite_reloaded_and_hash_verified") is not True
        or not isinstance(provenance_dmcache, Mapping)
        or provenance_dmcache.get("path") != str(bundle.dmcache_path)
        or provenance_dmcache.get("sha256") != bundle.dmcache_sha256
        or not isinstance(provenance_model, Mapping)
        or provenance_model.get("path") != str(bundle.model_cache_path)
        or provenance_model.get("sha256") != bundle.model_cache_sha256
    ):
        _generic_not_equivalent()

    attestation = payload.get("attestation")
    if not isinstance(attestation, Mapping):
        _generic_not_equivalent()
    file_records = attestation.get("files")
    tree_records = attestation.get("trees")
    expected_files = {
        str(bundle.input_contract_path): (
            len(bundle.input_contract_raw),
            bundle.input_contract_sha256,
        ),
        str(bundle.dmcache_path): (
            bundle.dmcache_path.stat().st_size,
            bundle.dmcache_sha256,
        ),
        str(bundle.model_cache_path): (
            bundle.model_cache_path.stat().st_size,
            bundle.model_cache_sha256,
        ),
        str(provenance_path): (provenance_size, provenance_sha),
    }
    observed_files: dict[str, tuple[int, str]] = {}
    if (
        not isinstance(file_records, list)
        or not isinstance(tree_records, list)
        or len(tree_records) > 1
    ):
        _generic_not_equivalent()
    for record in file_records:
        if not isinstance(record, Mapping):
            _generic_not_equivalent()
        path_value = record.get("path")
        if (
            record.get("schema_version") != "b0-attested-file-v1"
            or not isinstance(path_value, str)
            or path_value in observed_files
            or isinstance(record.get("size_bytes"), bool)
            or not isinstance(record.get("size_bytes"), int)
            or not isinstance(record.get("sha256"), str)
        ):
            _generic_not_equivalent()
        observed_files[path_value] = (
            record["size_bytes"],
            record["sha256"],
        )
    output_tree: Mapping[str, Any] | None = None
    if tree_records:
        tree_record = tree_records[0]
        if (
            not isinstance(tree_record, Mapping)
            or tree_record.get("path") != str(bundle.input_contract_path.parent)
        ):
            _generic_not_equivalent()
        try:
            current_tree = _current_tree_attestation(
                bundle.input_contract_path.parent
            )
        except PreRegistrationError:
            _generic_not_equivalent()
        if current_tree != dict(tree_record):
            _generic_not_equivalent()
        output_tree = dict(tree_record)

    attestation_payload = {"files": file_records, "trees": tree_records}
    attestation_sha = _canonical_json_sha256(attestation_payload)
    if (
        observed_files != expected_files
        or attestation.get("status") != "VERIFIED"
        or attestation.get("bundle_sha256") != attestation_sha
    ):
        _generic_not_equivalent()

    return _InputProducerMonitorEvidence(
        status_path=status,
        status_sha256=status_sha,
        status_size_bytes=status_size,
        child_argv=child_argv,
        child_argv_sha256=child_sha,
        attestation_bundle_sha256=attestation_sha,
        provenance_path=provenance,
        provenance_sha256=provenance_sha,
        provenance_size_bytes=provenance_size,
        output_tree=output_tree,
    )


def _exact_float(left: object, right: float) -> bool:
    try:
        return float(left).hex() == float(right).hex()
    except (TypeError, ValueError, OverflowError):
        return False


def _require_contract_path(container: Mapping[str, Any], key: str, label: str) -> Path:
    value = container.get(key)
    if not isinstance(value, str):
        _generic_not_equivalent()
    try:
        return _require_absolute_file(value, label=label)
    except PreRegistrationError:
        _generic_not_equivalent()
    raise AssertionError("unreachable")


def _load_generic_input_bundle(
    *, input_contract_path: Path | str, split_id: str
) -> _GenericInputBundle:
    """Validate the formal 115-frame cap50 contract and its physical assets.

    No frame role is inferred here.  The named split embedded in the immutable
    input contract is the only authority for the 93 reconstruction and 22
    held-out frames.
    """

    try:
        source = _require_absolute_file(
            input_contract_path, label="b0-input-contract-v1"
        )
        payload, raw_sha256 = input_contract.load_input_contract(source)
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != raw_sha256:
            _generic_not_equivalent()
        selected = input_contract.select_input_contract_split(payload, split_id)
    except (
        PreRegistrationError,
        OSError,
        input_contract.RouteInputNotEquivalent,
    ):
        _generic_not_equivalent()

    dataset_id = payload.get("dataset_id")
    coordinate_frame = payload.get("coordinate_frame")
    scale = payload.get("metres_per_model_unit")
    if (
        dataset_id != FORMAL_DATASET_ID
        or split_id != FORMAL_SPLIT_ID
        or coordinate_frame != FORMAL_COORDINATE_FRAME
        or not _exact_float(scale, FORMAL_METRES_PER_MODEL_UNIT)
    ):
        _generic_not_equivalent()

    policy = payload.get("transductive_policy")
    if (
        not isinstance(policy, Mapping)
        or policy.get("route_allowed") is not True
        or policy.get("quality_scoring_forbidden") is not False
        or selected.get("route_allowed", True) is not True
        or selected.get("quality_scoring_forbidden", False) is not False
    ):
        _generic_not_equivalent()

    dm_contract = payload.get("dmcache")
    model_contract = payload.get("model_cache")
    images_contract = payload.get("images")
    if not all(
        isinstance(value, Mapping)
        for value in (dm_contract, model_contract, images_contract)
    ):
        _generic_not_equivalent()
    dmcache_path = _require_contract_path(dm_contract, "path", "contract dmcache")
    model_cache_path = _require_contract_path(
        model_contract, "path", "contract model cache"
    )
    image_root_value = images_contract.get("root")
    if (
        not isinstance(image_root_value, str)
        or images_contract.get("raw_size_wh") != list(FORMAL_RAW_IMAGE_SIZE_WH)
    ):
        _generic_not_equivalent()
    try:
        image_root = _require_absolute_directory(
            image_root_value, label="contract image root"
        )
    except PreRegistrationError:
        _generic_not_equivalent()

    dmcache_sha256 = sha256_file(dmcache_path)
    model_cache_sha256 = sha256_file(model_cache_path)
    if (
        dmcache_sha256 != dm_contract.get("sha256")
        or model_cache_sha256 != model_contract.get("sha256")
    ):
        _generic_not_equivalent()

    universe = list(dm_contract.get("frame_order", ()))
    model_order = list(model_contract.get("frame_order", ()))
    reconstruction_role = selected.get("reconstruction")
    heldout_role = selected.get("heldout")
    if not isinstance(reconstruction_role, Mapping) or not isinstance(
        heldout_role, Mapping
    ):
        _generic_not_equivalent()
    reconstruction = list(reconstruction_role.get("frames", ()))
    heldout = list(heldout_role.get("frames", ()))
    if (
        len(universe) != FORMAL_UNIVERSE_COUNT
        or len(reconstruction) != FORMAL_RECONSTRUCTION_COUNT
        or len(heldout) != FORMAL_HELDOUT_COUNT
        or any("_tap-" not in name for name in universe)
    ):
        _generic_not_equivalent()
    reconstruction_sha256 = hash_frame_list(reconstruction)
    heldout_sha256 = hash_frame_list(heldout)
    if (
        dm_contract.get("frame_order_sha256")
        != FORMAL_UNIVERSE_FRAME_ORDER_SHA256
        or reconstruction_sha256 != FORMAL_RECONSTRUCTION_LIST_SHA256
        or heldout_sha256 != FORMAL_HELDOUT_LIST_SHA256
        or reconstruction_role.get("file_sha256") != reconstruction_sha256
        or reconstruction_role.get("semantic_sha256") != reconstruction_sha256
        or heldout_role.get("file_sha256") != heldout_sha256
        or heldout_role.get("semantic_sha256") != heldout_sha256
    ):
        _generic_not_equivalent()

    try:
        with np.load(dmcache_path, allow_pickle=False) as archive:
            if not {"frames", "dm", "sig"}.issubset(archive.files):
                _generic_not_equivalent()
            actual_dm_frames = archive["frames"].tolist()
            actual_depth = np.asarray(archive["dm"])
            actual_signature_array = np.asarray(archive["sig"])
            if actual_signature_array.shape != ():
                _generic_not_equivalent()
            actual_signature = str(actual_signature_array.item())
            if "metres_per_model_unit" in archive.files:
                archive_scale = np.asarray(archive["metres_per_model_unit"])
                if archive_scale.shape != () or not _exact_float(
                    archive_scale.item(), FORMAL_METRES_PER_MODEL_UNIT
                ):
                    _generic_not_equivalent()
    except (OSError, ValueError, KeyError):
        _generic_not_equivalent()
    depth_contract = dm_contract.get("depth")
    if (
        actual_dm_frames != universe
        or not isinstance(depth_contract, Mapping)
        or list(actual_depth.shape) != depth_contract.get("shape")
        or str(actual_depth.dtype) != depth_contract.get("dtype")
        or actual_depth.dtype != np.dtype(np.float32)
        or actual_signature != dm_contract.get("signature")
    ):
        _generic_not_equivalent()

    frame_to_index = {name: index for index, name in enumerate(universe)}
    try:
        reconstruction_indices = [frame_to_index[name] for name in reconstruction]
    except KeyError:
        _generic_not_equivalent()
    height, width = int(actual_depth.shape[1]), int(actual_depth.shape[2])
    reconstruction_total_raster_pixels = len(reconstruction) * height * width
    reconstruction_valid_depth_points = sum(
        int(
            np.count_nonzero(
                np.isfinite(actual_depth[index]) & (actual_depth[index] > 0.0)
            )
        )
        for index in reconstruction_indices
    )
    # AliceVision parses these budgets as positive signed 32-bit integers.
    if (
        reconstruction_total_raster_pixels <= 0
        or reconstruction_total_raster_pixels > 2_147_483_647
        or reconstruction_valid_depth_points <= 0
        or reconstruction_valid_depth_points + 1 > 2_147_483_647
    ):
        _generic_not_equivalent()

    try:
        with np.load(model_cache_path, allow_pickle=False) as archive:
            if not {"names", "K", "w2c"}.issubset(archive.files):
                _generic_not_equivalent()
            actual_model_names = archive["names"].tolist()
            K = np.asarray(archive["K"])
            w2c = np.asarray(archive["w2c"])
            if "metres_per_model_unit" in archive.files:
                archive_scale = np.asarray(archive["metres_per_model_unit"])
                if archive_scale.shape != () or not _exact_float(
                    archive_scale.item(), FORMAL_METRES_PER_MODEL_UNIT
                ):
                    _generic_not_equivalent()
    except (OSError, ValueError, KeyError):
        _generic_not_equivalent()
    if (
        actual_model_names != model_order
        or K.shape != (FORMAL_UNIVERSE_COUNT, 3, 3)
        or K.dtype != np.dtype(np.float32)
        or w2c.shape not in {
            (FORMAL_UNIVERSE_COUNT, 3, 4),
            (FORMAL_UNIVERSE_COUNT, 4, 4),
        }
        or w2c.dtype != np.dtype(np.float32)
        or not np.isfinite(K).all()
        or not np.isfinite(w2c).all()
    ):
        _generic_not_equivalent()

    by_name = images_contract.get("by_name")
    if not isinstance(by_name, Mapping):
        _generic_not_equivalent()
    actual_image_identities: dict[str, dict[str, Any]] = {}
    for name in universe:
        expected = by_name.get(name)
        image = image_root / name
        if not isinstance(expected, Mapping) or not image.is_file():
            _generic_not_equivalent()
        actual = {
            "sha256": sha256_file(image),
            "size_bytes": image.stat().st_size,
        }
        if actual != dict(expected):
            _generic_not_equivalent()
        actual_image_identities[name] = actual
    image_manifest_sha256 = input_contract.image_identity_manifest_sha256(
        universe, actual_image_identities
    )
    if image_manifest_sha256 != images_contract.get("root_manifest_sha256"):
        _generic_not_equivalent()

    return _GenericInputBundle(
        input_contract_path=source,
        input_contract_raw=raw,
        input_contract_sha256=raw_sha256,
        payload=payload,
        dataset_id=dataset_id,
        split_id=split_id,
        coordinate_frame=coordinate_frame,
        metres_per_model_unit=float(scale),
        dmcache_path=dmcache_path,
        model_cache_path=model_cache_path,
        image_root=image_root,
        universe=universe,
        reconstruction=reconstruction,
        heldout=heldout,
        dmcache_sha256=dmcache_sha256,
        model_cache_sha256=model_cache_sha256,
        image_manifest_sha256=image_manifest_sha256,
        reconstruction_list_sha256=reconstruction_sha256,
        heldout_list_sha256=heldout_sha256,
        dmcache_signature=actual_signature,
        depth_shape=list(actual_depth.shape),
        reconstruction_total_raster_pixels=reconstruction_total_raster_pixels,
        reconstruction_valid_depth_points=reconstruction_valid_depth_points,
    )


def _preflight_bundle(
    *,
    dmcache: Path | str,
    trio_model_lapa: Path | str,
    trio_refs: Path | str,
    spatial_manifest: Path | str,
    cap100_list: Path | str,
) -> _PreflightBundle:
    dmcache_path = _require_absolute_file(dmcache, label="dmcache")
    model_path = _require_absolute_file(trio_model_lapa, label="trio_model_lapa")
    trio_refs_path = _require_absolute_file(trio_refs, label="trio_refs")
    spatial_manifest_path = _require_absolute_file(
        spatial_manifest, label="tracked k414 spatial manifest"
    )
    cap100_list_path = _require_absolute_file(cap100_list, label="cap100 list")

    file_hashes = {
        "dmcache": sha256_file(dmcache_path),
        "trio_model_lapa": sha256_file(model_path),
        "trio_refs": sha256_file(trio_refs_path),
        "spatial_manifest": sha256_file(spatial_manifest_path),
        "cap100_list": sha256_file(cap100_list_path),
    }
    expected_file_hashes = {
        "dmcache": EXPECTED_DMCACHE_SHA256,
        "trio_model_lapa": EXPECTED_MODEL_CACHE_SHA256,
        "trio_refs": EXPECTED_TRIO_REFS_SHA256,
        "spatial_manifest": EXPECTED_SPATIAL_MANIFEST_SHA256,
        "cap100_list": EXPECTED_CAP_LIST_SHA256,
    }
    for label, expected in expected_file_hashes.items():
        _assert_hash(label, file_hashes[label], expected)

    cap_frames, cap_raw = read_cap_list(cap100_list_path)
    all_frames, depth, signature = _load_dmcache(dmcache_path)
    (
        model_names,
        intrinsics,
        world_to_camera,
        centers,
        model_arrays,
    ) = _load_model_cache(model_path)
    trio_pool, trio_ref_names = _load_trio_refs(trio_refs_path)
    derived_cap, spatial_names, spatial_schema = _load_spatial_manifest(
        spatial_manifest_path
    )

    if trio_pool != all_frames or trio_ref_names != all_frames:
        raise PreRegistrationError(
            f"{ROUTE_INPUT_NOT_EQUIVALENT}: trio_refs pool/refs order differs from dmcache"
        )
    if set(all_frames) != set(model_names):
        raise PreRegistrationError(
            f"{ROUTE_INPUT_NOT_EQUIVALENT}: dmcache/model exact-name set differs"
        )
    if not set(cap_frames).issubset(set(all_frames)):
        raise PreRegistrationError(
            f"{ROUTE_INPUT_NOT_EQUIVALENT}: cap100 does not fully join dmcache/model"
        )
    if derived_cap != cap_frames:
        raise PreRegistrationError(
            f"{ROUTE_INPUT_NOT_EQUIVALENT}: cap list does not match "
            "spatialOrder[:100] basenames"
        )
    manifest_only = set(spatial_names) - set(all_frames)
    if set(all_frames) - set(spatial_names) or len(manifest_only) != 1:
        raise PreRegistrationError(
            f"{ROUTE_INPUT_NOT_EQUIVALENT}: k414 manifest must contain exactly "
            "the 413 registered names plus one unregistered name"
        )

    cap_reconstruction, cap_heldout = split_cap100(cap_frames)
    full_reconstruction, full_heldout = split_full413(all_frames)
    list_hashes = {
        "cap100_all": hash_frame_list(cap_frames),
        "cap100_reconstruction": hash_frame_list(cap_reconstruction),
        "cap100_heldout": hash_frame_list(cap_heldout),
        "full413_all": hash_frame_list(all_frames),
        "full413_reconstruction": hash_frame_list(full_reconstruction),
        "full413_heldout": hash_frame_list(full_heldout),
    }
    expected_list_hashes = {
        "cap100_all": EXPECTED_CAP_LIST_SHA256,
        "cap100_reconstruction": EXPECTED_CAP_RECONSTRUCTION_SHA256,
        "cap100_heldout": EXPECTED_CAP_HELDOUT_SHA256,
        "full413_all": EXPECTED_FULL_ALL_SHA256,
        "full413_reconstruction": EXPECTED_FULL_RECONSTRUCTION_SHA256,
        "full413_heldout": EXPECTED_FULL_HELDOUT_SHA256,
    }
    for label, expected in expected_list_hashes.items():
        _assert_hash(label, list_hashes[label], expected)

    semantic = _semantic_inputs(
        all_frames,
        depth,
        model_names,
        intrinsics,
        world_to_camera,
        cap_reconstruction,
        cap_heldout,
        full_reconstruction,
        full_heldout,
    )
    return _PreflightBundle(
        dmcache_path=dmcache_path,
        model_path=model_path,
        trio_refs_path=trio_refs_path,
        spatial_manifest_path=spatial_manifest_path,
        cap100_list_path=cap100_list_path,
        file_hashes=file_hashes,
        cap_raw=cap_raw,
        all_frames=all_frames,
        depth=depth,
        signature=signature,
        model_names=model_names,
        intrinsics=intrinsics,
        world_to_camera=world_to_camera,
        centers=centers,
        model_arrays=model_arrays,
        trio_pool=trio_pool,
        trio_refs=trio_ref_names,
        spatial_schema=spatial_schema,
        spatial_names=spatial_names,
        cap_frames=cap_frames,
        cap_reconstruction=cap_reconstruction,
        cap_heldout=cap_heldout,
        full_reconstruction=full_reconstruction,
        full_heldout=full_heldout,
        list_hashes=list_hashes,
        semantic=semantic,
    )


def preflight(
    *,
    dmcache: Path | str,
    trio_model_lapa: Path | str,
    trio_refs: Path | str,
    spatial_manifest: Path | str,
    cap100_list: Path | str,
) -> dict[str, Any]:
    """Validate every frozen B0 input without creating or changing any path."""
    return _preflight_bundle(
        dmcache=dmcache,
        trio_model_lapa=trio_model_lapa,
        trio_refs=trio_refs,
        spatial_manifest=spatial_manifest,
        cap100_list=cap100_list,
    ).summary()


def _make_contract(execution_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": "B0_fuseCut_vs_6mm_TSDF",
        "frozen_authority": {
            "prompt_sha256": FROZEN_PROMPT_SHA256,
            "code_head": FROZEN_CODE_HEAD,
            "code_head_role": "base revision only; not the experiment implementation identity",
            **execution_identity,
            "data_sha256": {
                "dmcache_trio_ofull.npz": EXPECTED_DMCACHE_SHA256,
                "trio_model_lapa.npz": EXPECTED_MODEL_CACHE_SHA256,
                "trio_refs.json": EXPECTED_TRIO_REFS_SHA256,
                "k414_spatial_order_manifest.json": EXPECTED_SPATIAL_MANIFEST_SHA256,
                "image_list_100.txt": EXPECTED_CAP_LIST_SHA256,
            },
        },
        "random_seed": FROZEN_RANDOM_SEED,
        "preregistration_state": {
            "outputs_inspected": False,
            "meshes_generated": False,
            "metrics_generated": False,
            "statement": "No route mesh or metric output was inspected before freezing this contract.",
        },
        "only_experimental_variable": "meshing_backend",
        "dataset_identity": {
            "selected": "trio_spatial_first100_fallback",
            "selected_is_real_cap50_capture": False,
            "selected_derivation": (
                "first 100 basenames from the frozen k414 spatial order, joined "
                "to the 413-frame trio dmcache/model bundle"
            ),
            "real_cap50_capture": {
                "status": "NOT_SELECTED",
                "generated_or_modified_by_preregistration": False,
                "reason": (
                    "no independently verified common frozen dmcache/camera bundle "
                    "for the real cap50 capture was supplied to this contract"
                ),
            },
        },
        "claim_scope": (
            "fusion-held-out transductive observation-consistency; "
            "cache had all frames upstream"
        ),
        "not_ground_truth": True,
        "known_transductive_leakage": {
            "present": True,
            "reason": (
                "the frozen inference/pass2 dmcache was produced with information "
                "from the full registered sequence; held-out applies only at fusion"
            ),
            "forbidden_claims": [
                "independent held-out generalization",
                "true completeness",
                "true hole area",
                "ground-truth accuracy",
            ],
        },
        "same_for_both_arms": [
            "dmcache bytes and signature",
            "ordered reconstruction and held-out frame lists",
            "per-frame positive-finite mask",
            "camera-Z depth values",
            "intrinsics K",
            "world-to-camera matrices",
            "LAPA model coordinate frame",
            "prepared ROI and stratum masks",
            "held-out evaluator and metric code revision",
            "machine, environment, resource wrapper, and stop rules",
            "post-evaluation common Sim(3) visualization export",
        ],
        "routes": {
            "control": {
                "backend": "current 6 mm TSDF",
                "voxel_size_m": 0.006,
                "metric_voxel_size_m": 0.006,
                "model_frame_voxel_size_formula": "0.006 / frozen_sim3.scale",
                "sdf_trunc_voxels": 4.0,
            },
            "treatment": {
                "backend": "AliceVision fuseCut",
                "input_mode": "filtered depth maps",
                "source_depth_semantics": "camera-Z float32",
                "export_depth_semantics": "euclidean-ray float32",
                "camera_z_to_ray": (
                    "d_ray=d_z*sqrt(((u-cx)/fx)^2+((v-cy)/fy)^2+1)"
                ),
                "ray_to_z_roundtrip_max_relative_error": 1e-6,
                "similarity_map": "constant -1.0 neutral float32",
            },
        },
        "prohibited_route_specific_changes": [
            "ICP or any per-arm registration",
            "mask changes",
            "depth resampling or value changes",
            "cleanup, smoothing, decimation, hole filling, or route-specific cropping",
            "parameter tuning after inspecting any mesh or metric output",
        ],
        "coordinate_policy": {
            "reconstruction_and_evaluation": "LAPA model frame",
            "frozen_sim3": "apply exactly once after evaluation, identically to both arms",
            "frozen_sim3_model_to_arkit": FROZEN_SIM3,
            "distance_thresholds": (
                "metric thresholds are converted once with the common frozen Sim(3) scale"
            ),
        },
        "splits": {
            "cap100_quality": {
                "ordered_count": 100,
                "heldout_local_indices": list(CAP_HELDOUT_INDICES),
                "reconstruction_count": 81,
                "heldout_count": 19,
                "score_local_range_inclusive": [4, 94],
                "list_sha256": {
                    "all": EXPECTED_CAP_LIST_SHA256,
                    "reconstruction": EXPECTED_CAP_RECONSTRUCTION_SHA256,
                    "heldout": EXPECTED_CAP_HELDOUT_SHA256,
                },
                "supersedes_quality_gate": "48-frame/39-reconstruction gate",
            },
            "full413_quality": {
                "ordered_count": 413,
                "order": "frozen dmcache order",
                "heldout_global_indices": list(FULL_HELDOUT_INDICES),
                "selection": "every fifth global index starting at 4, inclusive through 409",
                "reconstruction_count": 331,
                "heldout_count": 82,
                "independent_of_cap100_spatial_roles": True,
                "list_sha256": {
                    "reconstruction": EXPECTED_FULL_RECONSTRUCTION_SHA256,
                    "heldout": EXPECTED_FULL_HELDOUT_SHA256,
                },
            },
            "full413_resource_topology": {
                "input_count": 413,
                "list_sha256": EXPECTED_FULL_ALL_SHA256,
                "quality_claim_allowed": False,
                "purposes": ["resource", "topology", "finite-output"],
            },
        },
        "execution_plan": {
            "cap100_quality": {
                "output_subdir": "runs/cap100_quality",
                "frame_list": "lists/cap100_reconstruction.txt",
                "heldout_list": "lists/cap100_heldout.txt",
                "arms": {"tsdf": "tsdf", "fusecut": "fusecut"},
            },
            "full413_quality": {
                "output_subdir": "runs/full413_quality",
                "requires": "cap100_quality PASS",
                "frame_list": "lists/full413_reconstruction.txt",
                "heldout_list": "lists/full413_heldout.txt",
                "arms": {"tsdf": "tsdf", "fusecut": "fusecut"},
            },
            "full413_resource_topology": {
                "output_subdir": "runs/full413_resource_topology",
                "frame_list": "lists/full413_all.txt",
                "quality_scoring_forbidden": True,
                "arms": {"tsdf": "tsdf", "fusecut": "fusecut"},
            },
            "leaf_output_policy": "every route --out leaf must not preexist",
            "legacy_48_frame_gate": {
                "allowed_purpose": "plumbing smoke only",
                "quality_decision_forbidden": True,
            },
            "commands_skeleton": {
                "tsdf": _monitor_prefix(
                    label="<RUN_LABEL>_tsdf", run_leaf="<TSDF_MONITOR_RUN>"
                )
                + [
                    "python3.11",
                    "tools/python/pw_tsdf_trio.py",
                    "ofull",
                    "6",
                    "--out",
                    "<TSDF_RUN>",
                    "--frame-list",
                    "<PREREG_ROOT>/<FRAME_LIST>",
                    "--dmcache",
                    "<ABS_DMCACHE>",
                    "--model-cache",
                    "<ABS_TRIO_MODEL_LAPA>",
                ],
                "fusecut_export": _monitor_prefix(
                    label="<RUN_LABEL>_fusecut_export",
                    run_leaf="<FUSECUT_EXPORT_MONITOR_RUN>",
                )
                + [
                    "python3.11",
                    "tools/python/b0_export_alicevision.py",
                    "--dmcache",
                    "<ABS_DMCACHE>",
                    "--model-cache",
                    "<ABS_TRIO_MODEL_LAPA>",
                    "--frame-list",
                    "<PREREG_ROOT>/<FRAME_LIST>",
                    "--image-root",
                    "<ABS_IMAGE_ROOT>",
                    "--manifest",
                    "<ABS_K414_SPATIAL_MANIFEST>",
                    "--out",
                    "<FUSECUT_EXPORT>",
                ],
                "alicevision_meshing": _monitor_prefix(
                    label="<RUN_LABEL>_fusecut", run_leaf="<FUSECUT_MONITOR_RUN>"
                )
                + [
                    "<ABS_ALICEVISION_MESHING>",
                    "--input",
                    "<FUSECUT_EXPORT>/scene.sfm",
                    "--depthMapsFolder",
                    "<FUSECUT_EXPORT>/depthMaps",
                    "--output",
                    "<FUSECUT_RUN>/dense.sfm",
                    "--outputMesh",
                    "<FUSECUT_RUN>/mesh.obj",
                    "--partitioning",
                    "singleBlock",
                    "--repartition",
                    "multiResolution",
                    "--estimateSpaceFromSfM",
                    "false",
                    "--addLandmarksToTheDensePointCloud",
                    "false",
                    "--colorizeOutput",
                    "false",
                    "--minStep",
                    "1",
                    "--maxInputPoints",
                    "<RECONSTRUCTION_TOTAL_RASTER_PIXELS>",
                    "--maxPoints",
                    "<RECONSTRUCTION_VALID_DEPTH_POINTS_PLUS_ONE>",
                    "--maxPointsPerVoxel",
                    "6000000",
                    "--minVis",
                    "2",
                    "--simFactor",
                    "15",
                    "--angleFactor",
                    "15",
                    "--universePercentile",
                    "0.999",
                    "--estimateSpaceMinObservations",
                    "3",
                    "--estimateSpaceMinObservationAngle",
                    "10",
                    "--pixSizeMarginInitCoef",
                    "2",
                    "--pixSizeMarginFinalCoef",
                    "1",
                    "--voteMarginFactor",
                    "4",
                    "--contributeMarginFactor",
                    "2",
                    "--simGaussianSizeInit",
                    "10",
                    "--simGaussianSize",
                    "10",
                    "--minAngleThreshold",
                    "0.1",
                    "--refineFuse",
                    "true",
                    "--helperPointsGridSize",
                    "10",
                    "--densifyNbFront",
                    "0",
                    "--densifyNbBack",
                    "0",
                    "--densifyScale",
                    "1",
                    "--maskHelperPointsWeight",
                    "0",
                    "--maskBorderSize",
                    "1",
                    "--nPixelSizeBehind",
                    "4",
                    "--fullWeight",
                    "1",
                    "--saveRawDensePointCloud",
                    "false",
                    "--voteFilteringForWeaklySupportedSurfaces",
                    "true",
                    "--invertTetrahedronBasedOnNeighborsNbIterations",
                    "10",
                    "--minSolidAngleRatio",
                    "0.2",
                    "--nbSolidAngleFilteringIterations",
                    "2",
                    "--maxNbConnectedHelperPoints",
                    "50",
                    "--exportDebugTetrahedralization",
                    "false",
                    "--seed",
                    str(FROZEN_RANDOM_SEED),
                    "--verboseLevel",
                    "info",
                ],
                "evaluation": {
                    "prepare": [
                        "python3.11",
                        "tools/python/b0_prepare_eval.py",
                        "--dmcache",
                        "<ABS_DMCACHE>",
                        "--model-cache",
                        "<ABS_TRIO_MODEL_LAPA>",
                        "--reconstruction-list",
                        "<PREREG_ROOT>/<FRAME_LIST>",
                        "--heldout-list",
                        "<PREREG_ROOT>/<HELDOUT_LIST>",
                        "--image-root",
                        "<ABS_IMAGE_ROOT>",
                        "--out",
                        "<PREPARED_EVALUATION_NPZ>",
                    ],
                    "evaluate_tsdf": [
                        "python3.11",
                        "tools/python/pw_mesh_bench.py",
                        "evaluate-mesh",
                        "--frames",
                        "<PREPARED_EVALUATION_NPZ>",
                        "--mesh",
                        "<TSDF_RUN>/mesh.ply",
                        "--mesh-frame",
                        "raw_lapa",
                        "--route-provenance",
                        "<TSDF_RUN>/provenance.json",
                        "--contract-digest",
                        "<ROUTE_SEMANTIC_MANIFEST_SHA256>",
                        "--evaluation-digest",
                        "<PREPARED_EVALUATION_DIGEST>",
                        "--out",
                        "<TSDF_EVALUATION_JSON>",
                    ],
                    "evaluate_fusecut": [
                        "python3.11",
                        "tools/python/pw_mesh_bench.py",
                        "evaluate-mesh",
                        "--frames",
                        "<PREPARED_EVALUATION_NPZ>",
                        "--mesh",
                        "<FUSECUT_RUN>/mesh.obj",
                        "--mesh-frame",
                        "alicevision_obj",
                        "--route-provenance",
                        "<FUSECUT_EXPORT>/provenance.json",
                        "--contract-digest",
                        "<ROUTE_SEMANTIC_MANIFEST_SHA256>",
                        "--evaluation-digest",
                        "<PREPARED_EVALUATION_DIGEST>",
                        "--out",
                        "<FUSECUT_EVALUATION_JSON>",
                    ],
                    "compare": [
                        "python3.11",
                        "tools/python/pw_mesh_bench.py",
                        "compare",
                        "--tsdf",
                        "<TSDF_EVALUATION_JSON>",
                        "--fusecut",
                        "<FUSECUT_EVALUATION_JSON>",
                        "--contract-digest",
                        "<ROUTE_SEMANTIC_MANIFEST_SHA256>",
                        "--evaluation-digest",
                        "<PREPARED_EVALUATION_DIGEST>",
                        "--dataset-profile",
                        "<CAP100_OR_FULL_PROFILE>",
                        "--bootstrap-replicates",
                        str(FROZEN_BOOTSTRAP_DRAWS),
                        "--bootstrap-seed",
                        str(FROZEN_RANDOM_SEED),
                        "--out",
                        "<COMPARISON_JSON>",
                    ],
                },
            },
        },
        "run_repetition_policy": {
            "registered_before_outputs": True,
            "seed": FROZEN_RANDOM_SEED,
            "primary_selection": "first successful run",
            "best_of_n_allowed": False,
            "output_based_selection_allowed": False,
            "execution_order": ["TSDF primary", "FuseCut primary"],
            "cap100_execution_order": [
                "TSDF primary",
                "FuseCut primary",
                "optional FuseCut nondeterminism repeat 1",
                "optional FuseCut nondeterminism repeat 2",
            ],
            "full413_quality_execution_order": [
                "TSDF primary",
                "FuseCut primary",
            ],
            "execution_order_applies_to": [
                "cap100_quality",
                "full413_quality",
                "full413_resource_topology",
            ],
            "fresh_process_per_route": True,
            "common_environment_required": True,
            "common_environment_rule": (
                "same frozen code revision, machine, process environment, resource "
                "wrapper, inputs, and stop rules for TSDF and FuseCut"
            ),
            "failed_attempt_policy": (
                "retain and report every failed attempt; an identical-config retry may "
                "seek the first successful run but may not tune from outputs"
            ),
            "tsdf": {
                "primary_runs": 1,
                "decision_run": "first successful fixed-seed run",
                "diagnostic_repeats_preregistered": 0,
            },
            "cap100_fusecut": {
                "primary_runs": 1,
                "decision_run": "first successful fixed-seed run",
                "additional_diagnostic_repeats_max": 2,
                "repeat_condition": "only if disk and time limits allow",
                "repeat_use": "nondeterminism diagnostic only",
                "may_replace_primary": False,
                "diagnostic_output_subdirs": [
                    "runs/cap100_quality/fusecut_repeat_01",
                    "runs/cap100_quality/fusecut_repeat_02",
                ],
            },
            "full413_quality": {
                "primary_selection": "first successful fixed-seed run",
                "output_based_selection_allowed": False,
                "best_of_n_allowed": False,
            },
        },
        "input_only_roi_and_strata": {
            "valid_mask": {
                "source": "positive finite frozen camera-Z depth",
                "erosion": "5-pixel Chebyshev radius (11x11 square; outside is invalid)",
            },
            "inner_geometry": {
                "neighbor_order": (
                    "ascending LAPA camera-center distance among reconstruction frames; "
                    "ties by frozen reconstruction-list order"
                ),
                "required_projected_neighbors": 3,
                "projection_border_px": 16,
                "visibility_source": "input cameras and masks only; never a route mesh",
            },
            "low_texture": {
                "srgb_eotf": (
                    "c/12.92 for c<=0.04045 else ((c+0.055)/1.055)^2.4"
                ),
                "linear_luminance": "0.2126*R + 0.7152*G + 0.0722*B",
                "sobel_gx_over_8": [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]],
                "sobel_gy_over_8": [[-1, -2, -1], [0, 0, 0], [1, 2, 1]],
                "statistic": "sqrt(mean_11x11(Gx^2+Gy^2))",
                "threshold_strict_less_than": 0.015,
                "minimum_border_px": 5,
            },
            "weak_support": {
                "candidate_count": 8,
                "candidate_order": "same nearest-reconstruction order as inner_geometry",
                "minimum_metric_camera_baseline_m": 0.04,
                "consistency": {
                    "roundtrip_reprojection_error_px_strict_less_than": 1.0,
                    "relative_camera_z_error_strict_less_than": 0.01,
                    "world_normal_dot_strict_greater_than": 0.5,
                    "sampling": (
                        "NumPy float64 projection/backprojection with deterministic "
                        "bilinear depth and nearest boolean-mask sampling"
                    ),
                },
                "support_count_inclusive_set": [3, 4],
            },
            "local_planar_shell": {
                "window": "11x11 valid observed points",
                "normal_spread": (
                    "maximum unoriented angular deviation from normalized mean <=5 deg"
                ),
                "plane_fit": "unweighted float64 SVD on observed LAPA points",
                "maximum_absolute_plane_residual_m": 0.005,
                "ray_hit_search_radius_m": 0.05,
                "ray_hit_cluster_radius_m": 0.0001,
                "minimum_distinct_shell_separation_m": 0.003,
                "maximum_unoriented_shell_normal_angle_deg": 20.0,
            },
            "implementation_boundary": (
                "mask preparation must use only NumPy/OpenCV semantics pinned by the "
                "runner environment and may not inspect route outputs"
            ),
        },
        "prepared_masks": {
            "status": "PENDING_PREPARE",
            "expected_artifact": "prepared_input_masks.npz",
            "sha256": None,
            "hash_fabricated": False,
            "quality_run_blocked_until_hashed": True,
        },
        "gate_delta_definition": (
            "fuseCut minus 6mm TSDF; percentage-point fields are literal pp; "
            "coverage passes >= min and error/topology deltas pass <= max"
        ),
        "gates": {
            "cap100_quality": {
                "coverage_delta_pp_min": -2.0,
                "applies_to_coverage": ["total", "low_texture", "weak_support"],
                "unsupported_gt_20mm_delta_pp_max": 2.0,
                "median_absrel_delta_pp_max": 0.5,
                "p95_absrel_delta_pp_max": 2.0,
                "median_normal_error_delta_max_deg": 2.0,
                "double_shell_rate_delta_pp_max": 1.0,
                "double_shell_p95_separation_delta_max_mm": 5.0,
                "nonmanifold_edge_fraction_max": 1e-4,
                "finite_vertices_and_faces_required": True,
                "source": "B0.6; no cap100 relaxation is permitted",
            },
            "full413_quality": {
                "coverage_delta_pp_min": -2.0,
                "applies_to_coverage": ["total", "low_texture", "weak_support"],
                "unsupported_gt_20mm_delta_pp_max": 2.0,
                "median_absrel_delta_pp_max": 0.5,
                "p95_absrel_delta_pp_max": 2.0,
                "median_normal_error_delta_max_deg": 2.0,
                "double_shell_rate_delta_pp_max": 1.0,
                "double_shell_p95_separation_delta_max_mm": 5.0,
                "nonmanifold_edge_fraction_max": 1e-4,
                "finite_vertices_and_faces_required": True,
                "source": "B0.6",
            },
        },
        "improvement_claim": {
            "unit": "paired held-out frame",
            "bootstrap_draws": FROZEN_BOOTSTRAP_DRAWS,
            "seed": FROZEN_RANDOM_SEED,
            "exact_draw_count_required": True,
            "alternate_draw_count_forbidden": True,
            "confidence_interval": "two-sided percentile 95%; use lower bound",
            "required_low_texture_coverage_lower_bound": 0.05,
            "required_weak_support_coverage_lower_bound": 0.05,
            "also_requires_all_noninferiority_gates": True,
        },
        "resource_limits_per_full_route": {
            "measured_on": "full413_resource_topology all-413 route",
            "peak_rss_gib_max": MONITOR_RESOURCE_LIMITS["peak_rss_gib_max"],
            "swap_growth_gib_max": MONITOR_RESOURCE_LIMITS["swap_growth_gib_max"],
            "wall_time_seconds_max": MONITOR_RESOURCE_LIMITS[
                "wall_time_seconds_max"
            ],
            "wall_time_hours_max": 4.0,
            "timeout_label": "TIMEOUT",
            "timeout_is_not_algorithm_impossibility": True,
            "enforced_by": "tools/python/b0_run_monitored.py",
        },
        "disk_guard": {
            "measurement_command": "df -k /",
            "start_available_gib_min": MONITOR_RESOURCE_LIMITS[
                "start_available_gib_min"
            ],
            "running_stop_below_available_gib": MONITOR_RESOURCE_LIMITS[
                "running_stop_below_available_gib"
            ],
            "sample_interval_seconds": MONITOR_RESOURCE_LIMITS[
                "sample_interval_seconds"
            ],
            "stop_label": "DISK_GUARD",
            "unit_definition": "GiB = available_KiB / 1048576",
            "enforced_by": "tools/python/b0_run_monitored.py",
        },
        "stop_conditions": [
            ROUTE_INPUT_NOT_EQUIVALENT,
            "prepared input-only mask artifact missing or unhashed",
            "output root already exists",
            "disk available below the runner's preregistered start/stop limits",
            "route exceeds a resource limit",
            "non-finite or invalid topology result",
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_hash_sidecar(path: Path) -> None:
    digest = sha256_file(path)
    path.with_suffix(".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )


def _make_generic_contract(
    *,
    bundle: _GenericInputBundle,
    producer_monitor: _InputProducerMonitorEvidence,
    execution_identity: dict[str, Any],
    output: Path,
    run_root: Path,
    code_root: Path,
) -> dict[str, Any]:
    raw_contract_path = (output / "input_contract.raw.json").resolve()
    generated_contract_path = (output / "contract.json").resolve()
    reconstruction_list_path = (
        output / "lists" / f"{bundle.split_id}_reconstruction.txt"
    ).resolve()
    heldout_list_path = (
        output / "lists" / f"{bundle.split_id}_heldout.txt"
    ).resolve()
    monitor_script = (code_root / "tools/python/b0_run_monitored.py").resolve()
    tsdf_script = (code_root / "tools/python/pw_tsdf_trio.py").resolve()
    exporter_script = (
        code_root / "tools/python/b0_export_alicevision.py"
    ).resolve()
    prepare_script = (code_root / "tools/python/b0_prepare_eval.py").resolve()
    evaluator_script = (code_root / "tools/python/pw_mesh_bench.py").resolve()

    python_executable = execution_identity["environment_identity"]["identity"][
        "python"
    ]["executable"]

    def monitored(
        phase: str,
        command: list[str],
        *,
        attest_files: Sequence[Path] = (),
        attest_trees: Sequence[Path] = (),
        require_prior_statuses: Sequence[Path] = (),
    ) -> list[str]:
        prefix = _monitor_prefix(
            label=f"{bundle.dataset_id}_{phase}",
            run_leaf=str(run_root / "monitor" / phase),
            python_executable=python_executable,
            preregistered_contract=str(generated_contract_path),
            phase=phase,
            attest_files=[str(path) for path in attest_files],
            attest_trees=[str(path) for path in attest_trees],
            require_prior_statuses=[str(path) for path in require_prior_statuses],
        )
        prefix[1] = str(monitor_script)
        return prefix + command

    common_input_values = {
        "input_contract_raw_sha256": bundle.input_contract_sha256,
        "dataset_id": bundle.dataset_id,
        "split_id": bundle.split_id,
        "dmcache_sha256": bundle.dmcache_sha256,
        "model_cache_sha256": bundle.model_cache_sha256,
        "images_root_manifest_sha256": bundle.image_manifest_sha256,
        "reconstruction_list_sha256": bundle.reconstruction_list_sha256,
        "heldout_list_sha256": bundle.heldout_list_sha256,
        "coordinate_frame": bundle.coordinate_frame,
        "metres_per_model_unit": bundle.metres_per_model_unit,
        "depth_semantics": "camera-Z float32 with positive-finite mask",
        "postprocessing": "none before common evaluation",
        "alignment": "none; no ICP or per-route scale fitting",
        "random_seed": FROZEN_RANDOM_SEED,
        "resource_limits": MONITOR_RESOURCE_LIMITS,
        "environment_sha256": execution_identity["environment_identity"]["sha256"],
        "input_producer_monitor_status_sha256": producer_monitor.status_sha256,
    }
    controlled_variable_table = [
        {
            "factor": factor,
            "tsdf": value,
            "fusecut": value,
            "only_experimental_difference": False,
        }
        for factor, value in common_input_values.items()
    ]
    controlled_variable_table.append(
        {
            "factor": "meshing_backend",
            "tsdf": "current physical 6 mm TSDF",
            "fusecut": "AliceVision fuseCut with frozen parameters",
            "only_experimental_difference": True,
        }
    )

    shared_route_args = [
        "--frame-list",
        str(reconstruction_list_path),
        "--dmcache",
        str(bundle.dmcache_path),
        "--model-cache",
        str(bundle.model_cache_path),
        "--image-root",
        str(bundle.image_root),
        "--input-contract",
        str(raw_contract_path),
        "--split-id",
        bundle.split_id,
    ]
    tsdf_child = [
        python_executable,
        str(tsdf_script),
        "ofull",
        "6",
        "--out",
        str(run_root / "tsdf"),
        *shared_route_args,
    ]
    export_child = [
        python_executable,
        str(exporter_script),
        *shared_route_args,
        "--out",
        str(run_root / "fusecut" / "export"),
    ]
    alicevision_child = [
            execution_identity["alicevision_binary"]["path"],
            "--input",
            str(run_root / "fusecut" / "export" / "scene.sfm"),
            "--depthMapsFolder",
            str(run_root / "fusecut" / "export" / "depthMaps"),
            "--output",
            str(run_root / "fusecut" / "dense.sfm"),
            "--outputMesh",
            str(run_root / "fusecut" / "mesh.obj"),
            "--partitioning",
            "singleBlock",
            "--repartition",
            "multiResolution",
            "--estimateSpaceFromSfM",
            "false",
            "--addLandmarksToTheDensePointCloud",
            "false",
            "--colorizeOutput",
            "false",
            "--minStep",
            "1",
            "--maxInputPoints",
            str(bundle.reconstruction_total_raster_pixels),
            "--maxPoints",
            str(bundle.reconstruction_valid_depth_points + 1),
            "--maxPointsPerVoxel",
            "6000000",
            "--minVis",
            "2",
            "--simFactor",
            "15",
            "--angleFactor",
            "15",
            "--universePercentile",
            "0.999",
            "--estimateSpaceMinObservations",
            "3",
            "--estimateSpaceMinObservationAngle",
            "10",
            "--pixSizeMarginInitCoef",
            "2",
            "--pixSizeMarginFinalCoef",
            "1",
            "--voteMarginFactor",
            "4",
            "--contributeMarginFactor",
            "2",
            "--simGaussianSizeInit",
            "10",
            "--simGaussianSize",
            "10",
            "--minAngleThreshold",
            "0.1",
            "--refineFuse",
            "true",
            "--helperPointsGridSize",
            "10",
            "--densifyNbFront",
            "0",
            "--densifyNbBack",
            "0",
            "--densifyScale",
            "1",
            "--maskHelperPointsWeight",
            "0",
            "--maskBorderSize",
            "1",
            "--nPixelSizeBehind",
            "4",
            "--fullWeight",
            "1",
            "--saveRawDensePointCloud",
            "false",
            "--voteFilteringForWeaklySupportedSurfaces",
            "true",
            "--invertTetrahedronBasedOnNeighborsNbIterations",
            "10",
            "--minSolidAngleRatio",
            "0.2",
            "--nbSolidAngleFilteringIterations",
            "2",
            "--maxNbConnectedHelperPoints",
            "50",
            "--exportDebugTetrahedralization",
            "false",
            "--seed",
            str(FROZEN_RANDOM_SEED),
            "--verboseLevel",
            "info",
    ]
    prepared_npz = str(run_root / "evaluation" / "prepared_input_masks.npz")
    prepared_provenance = prepared_npz + ".provenance.json"
    prepare_child = [
            python_executable,
            str(prepare_script),
            "--dmcache",
            str(bundle.dmcache_path),
            "--model-cache",
            str(bundle.model_cache_path),
            "--reconstruction-list",
            str(reconstruction_list_path),
            "--heldout-list",
            str(heldout_list_path),
            "--image-root",
            str(bundle.image_root),
            "--input-contract",
            str(raw_contract_path),
            "--split-id",
            bundle.split_id,
            "--out",
            prepared_npz,
    ]
    evaluate_tsdf_child = [
            python_executable,
            str(evaluator_script),
            "evaluate-mesh",
            "--frames",
            prepared_npz,
            "--mesh",
            str(run_root / "tsdf" / "mesh.ply"),
            "--mesh-frame",
            "contract_model",
            "--route-provenance",
            str(run_root / "tsdf" / "provenance.json"),
            "--route-monitor-status",
            str(run_root / "monitor" / "tsdf_meshing" / "status.json"),
            "--prepared-provenance",
            prepared_provenance,
            "--preregistered-contract",
            str(generated_contract_path),
            "--input-contract",
            str(raw_contract_path),
            "--split-id",
            bundle.split_id,
            "--out",
            str(run_root / "evaluation" / "tsdf.json"),
    ]
    evaluate_fusecut_child = [
            python_executable,
            str(evaluator_script),
            "evaluate-mesh",
            "--frames",
            prepared_npz,
            "--mesh",
            str(run_root / "fusecut" / "mesh.obj"),
            "--mesh-frame",
            "alicevision_obj",
            "--route-provenance",
            str(run_root / "fusecut" / "export" / "provenance.json"),
            "--route-monitor-status",
            str(run_root / "monitor" / "fusecut_meshing" / "status.json"),
            "--prepared-provenance",
            prepared_provenance,
            "--preregistered-contract",
            str(generated_contract_path),
            "--input-contract",
            str(raw_contract_path),
            "--split-id",
            bundle.split_id,
            "--out",
            str(run_root / "evaluation" / "fusecut.json"),
    ]
    compare_child = [
            python_executable,
            str(evaluator_script),
            "compare",
            "--tsdf",
            str(run_root / "evaluation" / "tsdf.json"),
            "--fusecut",
            str(run_root / "evaluation" / "fusecut.json"),
            "--frames",
            prepared_npz,
            "--prepared-provenance",
            prepared_provenance,
            "--preregistered-contract",
            str(generated_contract_path),
            "--input-contract",
            str(raw_contract_path),
            "--split-id",
            bundle.split_id,
            "--bootstrap-replicates",
            str(FROZEN_BOOTSTRAP_DRAWS),
            "--bootstrap-seed",
            str(FROZEN_RANDOM_SEED),
            "--out",
            str(run_root / "evaluation" / "comparison.json"),
    ]
    formal_children = {
        "tsdf_meshing": tsdf_child,
        "fusecut_export": export_child,
        "fusecut_meshing": alicevision_child,
        "evaluation_prepare": prepare_child,
        "evaluate_tsdf": evaluate_tsdf_child,
        "evaluate_fusecut": evaluate_fusecut_child,
        "evaluation_compare": compare_child,
    }
    formal_runner_bindings = {
        phase: {
            "child_argv": child,
            "child_argv_sha256": _canonical_json_sha256(child),
        }
        for phase, child in formal_children.items()
    }
    tsdf_status = run_root / "monitor" / "tsdf_meshing" / "status.json"
    export_status = run_root / "monitor" / "fusecut_export" / "status.json"
    fusecut_status = run_root / "monitor" / "fusecut_meshing" / "status.json"
    prepare_status = run_root / "monitor" / "evaluation_prepare" / "status.json"
    evaluate_tsdf_status = run_root / "monitor" / "evaluate_tsdf" / "status.json"
    evaluate_fusecut_status = (
        run_root / "monitor" / "evaluate_fusecut" / "status.json"
    )
    tsdf_command = monitored(
        "tsdf_meshing",
        tsdf_child,
        attest_files=(
            run_root / "tsdf" / "mesh.ply",
            run_root / "tsdf" / "provenance.json",
        ),
    )
    export_command = monitored(
        "fusecut_export",
        export_child,
        attest_files=(run_root / "fusecut" / "export" / "provenance.json",),
        attest_trees=(run_root / "fusecut" / "export",),
    )
    alicevision_command = monitored(
        "fusecut_meshing",
        alicevision_child,
        attest_files=(
            run_root / "fusecut" / "mesh.obj",
            run_root / "fusecut" / "dense.sfm",
        ),
        require_prior_statuses=(export_status,),
    )
    evaluation = {
        "prepare": monitored(
            "evaluation_prepare",
            prepare_child,
            attest_files=(Path(prepared_npz), Path(prepared_provenance)),
        ),
        "evaluate_tsdf": monitored(
            "evaluate_tsdf",
            evaluate_tsdf_child,
            attest_files=(run_root / "evaluation" / "tsdf.json",),
            require_prior_statuses=(tsdf_status, prepare_status),
        ),
        "evaluate_fusecut": monitored(
            "evaluate_fusecut",
            evaluate_fusecut_child,
            attest_files=(run_root / "evaluation" / "fusecut.json",),
            require_prior_statuses=(fusecut_status, prepare_status),
        ),
        "compare": monitored(
            "evaluation_compare",
            compare_child,
            attest_files=(run_root / "evaluation" / "comparison.json",),
            require_prior_statuses=(
                evaluate_tsdf_status,
                evaluate_fusecut_status,
            ),
        ),
    }

    strict_gate = {
        "coverage_delta_min": -0.02,
        "unsupported_gt_20mm_delta_max": 0.02,
        "median_absrel_delta_max": 0.005,
        "p95_absrel_delta_max": 0.02,
        "median_normal_error_delta_max_deg": 2.0,
        "double_shell_rate_delta_max": 0.01,
        "double_shell_p95_separation_delta_max_m": 0.005,
        "nonmanifold_edge_fraction_max": 1e-4,
        "finite_vertices_and_faces_required": True,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": "B0_fuseCut_vs_6mm_TSDF",
        "dataset_id": bundle.dataset_id,
        "input_split_id": bundle.split_id,
        "only_experimental_variable": "meshing_backend",
        "frozen_authority": {
            "prompt_sha256": FROZEN_PROMPT_SHA256,
            "code_head": FROZEN_CODE_HEAD,
            "code_head_role": (
                "base revision only; dirty code bundle is the implementation identity"
            ),
            **execution_identity,
            "input_contract": {
                "schema_version": input_contract.INPUT_CONTRACT_SCHEMA_VERSION,
                "source_path": str(bundle.input_contract_path),
                "vendored_raw_file": "input_contract.raw.json",
                "raw_sha256": bundle.input_contract_sha256,
                "dataset_id": bundle.dataset_id,
                "split_id": bundle.split_id,
                "coordinate_frame": bundle.coordinate_frame,
                "metres_per_model_unit": bundle.metres_per_model_unit,
                "universe_count": len(bundle.universe),
                "reconstruction_count": len(bundle.reconstruction),
                "heldout_count": len(bundle.heldout),
                "universe_frame_order_sha256": (
                    FORMAL_UNIVERSE_FRAME_ORDER_SHA256
                ),
                "reconstruction_list_sha256": (
                    bundle.reconstruction_list_sha256
                ),
                "heldout_list_sha256": bundle.heldout_list_sha256,
            },
            "data_sha256": {
                "dmcache": bundle.dmcache_sha256,
                "model_cache": bundle.model_cache_sha256,
                "images_root_manifest": bundle.image_manifest_sha256,
            },
            "input_producer_monitor": {
                "status_path": str(producer_monitor.status_path),
                "status_sha256": producer_monitor.status_sha256,
                "status_size_bytes": producer_monitor.status_size_bytes,
                "verdict": "PASS",
                "child_argv": producer_monitor.child_argv,
                "child_argv_sha256": producer_monitor.child_argv_sha256,
                "attestation_bundle_sha256": (
                    producer_monitor.attestation_bundle_sha256
                ),
                "provenance_path": str(producer_monitor.provenance_path),
                "provenance_sha256": producer_monitor.provenance_sha256,
                "provenance_size_bytes": producer_monitor.provenance_size_bytes,
                "output_tree": producer_monitor.output_tree,
            },
        },
        "preregistration_state": {
            "outputs_inspected": False,
            "meshes_generated": False,
            "metrics_generated": False,
        },
        "claim_scope": (
            "fusion-held-out transductive observation-consistency; not ground truth"
        ),
        "controlled_variable_table": controlled_variable_table,
        "splits": {
            bundle.dataset_id: {
                "source_input_contract_split_id": bundle.split_id,
                "universe_count": len(bundle.universe),
                "reconstruction_count": len(bundle.reconstruction),
                "heldout_count": len(bundle.heldout),
                "quality_claim_allowed": True,
                "list_sha256": {
                    "reconstruction": bundle.reconstruction_list_sha256,
                    "heldout": bundle.heldout_list_sha256,
                },
                "list_files": {
                    "reconstruction": str(reconstruction_list_path),
                    "heldout": str(heldout_list_path),
                },
            }
        },
        "gates": {"b0_prompt_strict": strict_gate},
        "improvement_claim": {
            "unit": "paired held-out frame",
            "bootstrap_draws": FROZEN_BOOTSTRAP_DRAWS,
            "seed": FROZEN_RANDOM_SEED,
            "confidence_interval": "two-sided percentile 95%; use lower bound",
            "required_low_texture_coverage_lower_bound": 0.05,
            "required_weak_support_coverage_lower_bound": 0.05,
            "also_requires_all_noninferiority_gates": True,
        },
        "execution_plan": {
            bundle.dataset_id: {
                "input_contract_split_id": bundle.split_id,
                "frame_list": str(reconstruction_list_path),
                "heldout_list": str(heldout_list_path),
                "quality_scoring_forbidden": False,
            },
            "shared_input_binding": {
                "applies_to": [
                    "tsdf_meshing",
                    "fusecut_export",
                    "evaluation_prepare",
                    "evaluate_tsdf",
                    "evaluate_fusecut",
                    "compare",
                ],
                "input_contract": str(raw_contract_path),
                "input_contract_raw_sha256": bundle.input_contract_sha256,
                "split_id": bundle.split_id,
                "dataset_id": bundle.dataset_id,
                "preregistered_contract": str(generated_contract_path),
                "note": (
                    "route CLIs consume input_contract+split directly; evaluator "
                    "CLIs consume this generated preregistration+dataset binding"
                ),
            },
            "commands": {
                "tsdf_meshing": tsdf_command,
                "fusecut_export": export_command,
                "fusecut_meshing": alicevision_command,
                "evaluation": evaluation,
            },
            "formal_runner_bindings": formal_runner_bindings,
            "run_root_rule": {
                "path": str(run_root),
                "must_be_absolute": True,
                "must_not_exist_at_preregistration": True,
                "observed_absent_at_preregistration": True,
                "created_by_preregistration": False,
            },
            "alicevision_point_budgets": {
                "depth_shape": bundle.depth_shape,
                "reconstruction_frame_count": len(bundle.reconstruction),
                "maxInputPoints": bundle.reconstruction_total_raster_pixels,
                "maxInputPoints_formula": (
                    "len(reconstruction) * depth_height * depth_width"
                ),
                "valid_depth_predicate": "isfinite(depth) and depth > 0",
                "valid_depth_scope": "reconstruction frame rows only",
                "reconstruction_valid_depth_points": (
                    bundle.reconstruction_valid_depth_points
                ),
                "maxPoints": bundle.reconstruction_valid_depth_points + 1,
                "maxPoints_formula": (
                    "count(isfinite(depth) & (depth > 0) over reconstruction "
                    "frame rows only) + 1"
                ),
                "source": "physically hash-verified dmcache selected by the exact input contract split",
            },
        },
        "resource_limits": {
            **MONITOR_RESOURCE_LIMITS,
            "resource_poll_seconds": 1,
            "enforced_by": str(monitor_script),
        },
        "run_repetition_policy": {
            "seed": FROZEN_RANDOM_SEED,
            "primary_selection": "first successful run",
            "best_of_n_allowed": False,
            "output_based_selection_allowed": False,
            "failed_attempts_preserved": True,
        },
        "prepared_masks": {
            "status": "PENDING_PREPARE",
            "quality_run_blocked_until_hashed": True,
        },
    }


def preregister_from_input_contract(
    *,
    input_contract_path: Path | str,
    split_id: str,
    code_root: Path | str,
    alicevision_binary: Path | str,
    input_producer_monitor_status: Path | str,
    run_root: Path | str,
    out: Path | str,
) -> dict[str, Any]:
    """Freeze the formal real-cap50 mesher-only A/B before any route output."""

    output = Path(out)
    if os.path.lexists(output):
        raise FileExistsError(f"output path already exists: {output}")
    supplied_run_root = Path(run_root)
    if not supplied_run_root.is_absolute():
        raise PreRegistrationError(
            f"run_root must be an absolute path: {supplied_run_root}"
        )
    resolved_run_root = supplied_run_root.resolve()
    if os.path.lexists(resolved_run_root):
        raise FileExistsError(f"run_root already exists: {resolved_run_root}")
    resolved_output = output.resolve()
    if (
        resolved_output == resolved_run_root
        or resolved_output.is_relative_to(resolved_run_root)
        or resolved_run_root.is_relative_to(resolved_output)
    ):
        raise PreRegistrationError(
            "run_root and preregistration output must be disjoint paths"
        )
    bundle = _load_generic_input_bundle(
        input_contract_path=input_contract_path, split_id=split_id
    )
    resolved_code_root = _require_absolute_directory(code_root, label="code_root")
    execution_identity = _freeze_execution_identity(
        code_root=resolved_code_root, alicevision_binary=alicevision_binary
    )
    producer_monitor = _load_input_producer_monitor_evidence(
        status_path=input_producer_monitor_status,
        bundle=bundle,
        code_root=resolved_code_root,
        execution_identity=execution_identity,
    )
    contract = _make_generic_contract(
        bundle=bundle,
        producer_monitor=producer_monitor,
        execution_identity=execution_identity,
        output=resolved_output,
        run_root=resolved_run_root,
        code_root=resolved_code_root,
    )

    # Recheck the raw authority after all potentially expensive physical hashes
    # and before the first write, so an in-place mutation cannot be silently
    # represented by the earlier digest.
    if (
        bundle.input_contract_path.read_bytes() != bundle.input_contract_raw
        or sha256_file(bundle.dmcache_path) != bundle.dmcache_sha256
        or sha256_file(bundle.model_cache_path) != bundle.model_cache_sha256
    ):
        _generic_not_equivalent()
    images = bundle.payload["images"]["by_name"]
    for name in bundle.universe:
        image = bundle.image_root / name
        expected = images[name]
        if (
            not image.is_file()
            or image.stat().st_size != expected["size_bytes"]
            or sha256_file(image) != expected["sha256"]
        ):
            _generic_not_equivalent()
    source_state = execution_identity["source_state"]["dirty_code_bundle"]
    for entry in source_state["files"]:
        if sha256_file(entry["absolute_path"]) != entry["sha256"]:
            _generic_not_equivalent()
    alicevision = execution_identity["alicevision_binary"]
    if sha256_file(alicevision["path"]) != alicevision["sha256"]:
        _generic_not_equivalent()
    try:
        _, producer_status_size, producer_status_sha = (
            _canonical_regular_file_identity(
                producer_monitor.status_path,
                label="input producer monitor status",
            )
        )
        _, producer_provenance_size, producer_provenance_sha = (
            _canonical_regular_file_identity(
                producer_monitor.provenance_path,
                label="input producer provenance",
            )
        )
    except PreRegistrationError:
        _generic_not_equivalent()
    if (
        producer_status_size != producer_monitor.status_size_bytes
        or producer_status_sha != producer_monitor.status_sha256
        or producer_provenance_size != producer_monitor.provenance_size_bytes
        or producer_provenance_sha != producer_monitor.provenance_sha256
    ):
        _generic_not_equivalent()
    if producer_monitor.output_tree is not None:
        try:
            current_producer_tree = _current_tree_attestation(
                bundle.input_contract_path.parent
            )
        except PreRegistrationError:
            _generic_not_equivalent()
        if current_producer_tree != dict(producer_monitor.output_tree):
            _generic_not_equivalent()
    if os.path.lexists(resolved_run_root):
        raise FileExistsError(f"run_root already exists: {resolved_run_root}")

    output.mkdir(parents=True, exist_ok=False)
    lists = output / "lists"
    lists.mkdir()
    (lists / f"{bundle.split_id}_reconstruction.txt").write_bytes(
        _frame_list_bytes(bundle.reconstruction)
    )
    (lists / f"{bundle.split_id}_heldout.txt").write_bytes(
        _frame_list_bytes(bundle.heldout)
    )
    raw_copy = output / "input_contract.raw.json"
    raw_copy.write_bytes(bundle.input_contract_raw)
    _write_hash_sidecar(raw_copy)
    _write_json(output / "contract.json", contract)
    _write_hash_sidecar(output / "contract.json")
    return {
        "status": "FROZEN",
        "output": str(output.resolve()),
        "run_root": str(resolved_run_root),
        "contract_sha256": sha256_file(output / "contract.json"),
        "input_contract_raw_sha256": bundle.input_contract_sha256,
        "dataset_id": bundle.dataset_id,
        "split_id": bundle.split_id,
        "universe_count": len(bundle.universe),
        "reconstruction_count": len(bundle.reconstruction),
        "heldout_count": len(bundle.heldout),
        "input_producer_monitor_status_sha256": producer_monitor.status_sha256,
    }


def preregister(
    *,
    dmcache: Path | str,
    trio_model_lapa: Path | str,
    trio_refs: Path | str,
    spatial_manifest: Path | str,
    cap100_list: Path | str,
    code_root: Path | str,
    alicevision_binary: Path | str,
    out: Path | str,
) -> dict[str, Any]:
    output = Path(out)
    if os.path.lexists(output):
        raise FileExistsError(f"output path already exists: {output}")
    bundle = _preflight_bundle(
        dmcache=dmcache,
        trio_model_lapa=trio_model_lapa,
        trio_refs=trio_refs,
        spatial_manifest=spatial_manifest,
        cap100_list=cap100_list,
    )
    execution_identity = _freeze_execution_identity(
        code_root=code_root, alicevision_binary=alicevision_binary
    )

    split_manifest = {
        "cap100": {
            "all": _describe_list("lists/cap100_all.txt", bundle.cap_frames),
            "reconstruction": _describe_list(
                "lists/cap100_reconstruction.txt", bundle.cap_reconstruction
            ),
            "heldout": _describe_list(
                "lists/cap100_heldout.txt", bundle.cap_heldout
            ),
            "heldout_local_indices": list(CAP_HELDOUT_INDICES),
            "order": "frozen spatial cap order",
        },
        "full413_quality": {
            "reconstruction": _describe_list(
                "lists/full413_reconstruction.txt", bundle.full_reconstruction
            ),
            "heldout": _describe_list(
                "lists/full413_heldout.txt", bundle.full_heldout
            ),
            "heldout_global_indices": list(FULL_HELDOUT_INDICES),
            "order": "frozen dmcache order",
            "selection": "global indices 4,9,...,409",
        },
        "full413_resource_topology": {
            "all": _describe_list("lists/full413_all.txt", bundle.all_frames),
            "quality_scoring_forbidden": True,
            "separate_from_full413_quality": True,
        },
    }

    manifest_only = sorted(set(bundle.spatial_names) - set(bundle.all_frames))
    spatial_derivation: dict[str, Any] = {
        "status": "VERIFIED",
        "path": str(bundle.spatial_manifest_path),
        "repository_path": SPATIAL_MANIFEST_REPOSITORY_PATH,
        "tracked_at_frozen_code_head": True,
        "schema_version": bundle.spatial_schema,
        "sha256": bundle.file_hashes["spatial_manifest"],
        "size_bytes": bundle.spatial_manifest_path.stat().st_size,
        "frame_count": len(bundle.spatial_names),
        "registered_join_count": len(bundle.all_frames),
        "manifest_only_names": manifest_only,
        "derivation": "basename(frames[index].jpegPath) for spatialOrder[:100]",
        "exact_cap100_match": True,
    }

    input_manifest = {
        "schema_version": "b0-input-manifest-v1",
        "all_supplied_input_paths_absolute": True,
        "dmcache": {
            "path": str(bundle.dmcache_path),
            "sha256": bundle.file_hashes["dmcache"],
            "size_bytes": bundle.dmcache_path.stat().st_size,
            "arrays": {
                "frames": {"shape": [413], "unique": True},
                "dm": {
                    "shape": list(bundle.depth.shape),
                    "dtype": str(bundle.depth.dtype),
                },
                "sig": bundle.signature,
            },
        },
        "trio_model_lapa": {
            "path": str(bundle.model_path),
            "sha256": bundle.file_hashes["trio_model_lapa"],
            "size_bytes": bundle.model_path.stat().st_size,
            "arrays": bundle.model_arrays,
            "coordinate_frame": "LAPA model frame",
        },
        "trio_refs": {
            "path": str(bundle.trio_refs_path),
            "sha256": bundle.file_hashes["trio_refs"],
            "size_bytes": bundle.trio_refs_path.stat().st_size,
            "arrays": {
                "pool": {"count": len(bundle.trio_pool), "unique": True},
                "refs": {"count": len(bundle.trio_refs), "unique": True},
            },
            "pool_refs_and_dmcache_order_identical": True,
        },
        "spatial_manifest": spatial_derivation,
        "cap100_list": {
            "path": str(bundle.cap100_list_path),
            "sha256": bundle.file_hashes["cap100_list"],
            "size_bytes": len(bundle.cap_raw),
            "vendored_copy": "lists/cap100_all.txt",
            "canonical_utf8_final_newline": True,
        },
        "joins": {
            "trio_refs_pool_refs_dmcache_exact_order": True,
            "dmcache_model_exact_name_set": True,
            "spatial_manifest_registered_join_count": 413,
            "cap100_unique_count": 100,
            "cap100_joined_dmcache_count": 100,
            "cap100_joined_model_count": 100,
            "cap100_matches_spatial_order_first_100": True,
        },
        "splits": split_manifest,
        "semantic_inputs": bundle.semantic,
    }

    contract = _make_contract(execution_identity)
    contract["input_manifest"] = {
        "file": "input_manifest.json",
        "semantic_all413_manifest_sha256": bundle.semantic[
            "all413_manifest_sha256"
        ],
    }
    contract["execution_plan"]["resolved_bindings"] = {
        "<PREREG_ROOT>": str(output.resolve()),
        "<ABS_DMCACHE>": str(bundle.dmcache_path),
        "<ABS_TRIO_MODEL_LAPA>": str(bundle.model_path),
        "<ABS_TRIO_REFS>": str(bundle.trio_refs_path),
        "<ABS_K414_SPATIAL_MANIFEST>": str(bundle.spatial_manifest_path),
        "<ABS_CAP100_LIST>": str(bundle.cap100_list_path),
        "<ABS_ALICEVISION_MESHING>": execution_identity["alicevision_binary"][
            "path"
        ],
        "<CODE_ROOT>": str(Path(code_root).resolve()),
    }
    contract["source_readiness"] = {
        "frozen_inputs": "VERIFIED",
        "cap_spatial_derivation": "VERIFIED",
        "quality_run_ready": False,
        "note": "pre-registration is frozen; mask preparation remains a separate input-only step",
    }

    # All validation and expensive hashing finish before the first output write.
    # mkdir(exist_ok=False) closes the race after the initial lexists check.
    output.mkdir(parents=True, exist_ok=False)
    lists_dir = output / "lists"
    lists_dir.mkdir()
    list_payloads = {
        "cap100_all.txt": bundle.cap_frames,
        "cap100_reconstruction.txt": bundle.cap_reconstruction,
        "cap100_heldout.txt": bundle.cap_heldout,
        "full413_all.txt": bundle.all_frames,
        "full413_reconstruction.txt": bundle.full_reconstruction,
        "full413_heldout.txt": bundle.full_heldout,
    }
    for filename, names in list_payloads.items():
        (lists_dir / filename).write_bytes(_frame_list_bytes(names))
    # Prove that vendoring did not normalize or rewrite the untracked source list.
    if (lists_dir / "cap100_all.txt").read_bytes() != bundle.cap_raw:
        raise AssertionError("vendored cap100 bytes differ from frozen source")

    _write_json(output / "input_manifest.json", input_manifest)
    _write_hash_sidecar(output / "input_manifest.json")
    _write_json(output / "contract.json", contract)
    _write_hash_sidecar(output / "contract.json")

    return {
        "status": "FROZEN",
        "output": str(output.resolve()),
        "input_manifest_sha256": sha256_file(output / "input_manifest.json"),
        "contract_sha256": sha256_file(output / "contract.json"),
        "cap100": {"reconstruction": 81, "heldout": 19},
        "full413_quality": {"reconstruction": 331, "heldout": 82},
        "full413_resource_topology": {"all": 413},
        "prepared_masks": "PENDING_PREPARE",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze a generic b0-input-contract-v1 split for the formal "
            "fuseCut-vs-TSDF experiment."
        )
    )
    parser.add_argument(
        "--input-contract",
        required=True,
        type=Path,
        help=(
            "Absolute immutable b0-input-contract-v1 JSON containing physical "
            "dmcache/model/image paths and their frozen identities."
        ),
    )
    parser.add_argument(
        "--split-id",
        required=True,
        help="Exact pre-existing split key; preregistration never derives a split.",
    )
    parser.add_argument(
        "--code-root",
        required=True,
        type=Path,
        help=(
            "Absolute repository/worktree root containing every frozen dirty "
            "B0 execution script, including b0_run_monitored.py."
        ),
    )
    parser.add_argument(
        "--alicevision-binary",
        required=True,
        type=Path,
        help="Absolute executable AliceVision meshing binary to hash and freeze.",
    )
    parser.add_argument(
        "--input-producer-monitor-status",
        required=True,
        type=Path,
        help=(
            "Absolute PASS status from the monitored full-115 common-cache "
            "producer, with exact artifact attestations."
        ),
    )
    parser.add_argument(
        "--run-root",
        required=True,
        type=Path,
        help=(
            "Absolute execution root that does not yet exist; preregistration "
            "records it but never creates it."
        ),
    )
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = preregister_from_input_contract(
            input_contract_path=args.input_contract,
            split_id=args.split_id,
            code_root=args.code_root,
            alicevision_binary=args.alicevision_binary,
            input_producer_monitor_status=args.input_producer_monitor_status,
            run_root=args.run_root,
            out=args.out,
        )
    except (PreRegistrationError, FileExistsError, OSError) as exc:
        print(f"B0_PREREGISTRATION_FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
