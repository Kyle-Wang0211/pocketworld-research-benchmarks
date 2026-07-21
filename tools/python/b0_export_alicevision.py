#!/usr/bin/env python3
"""Export frozen B0 observations to AliceVision fuseCut inputs.

This adapter is intentionally manifest-driven and fail-closed.  It performs no
confidence filtering, smoothing, coordinate alignment, or pose optimization:
fuseCut and TSDF must differ only in the meshing algorithm.  Camera-Z depths are
converted to AliceVision's Euclidean-ray encoding at the final serialization
boundary, while semantic hashes cover the original camera-Z inputs.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Mapping, Sequence

import numpy as np

import b0_input_contract as contract


# OpenCV reads the serialized files back as part of the production export gate.
# The codec switch is consulted while cv2 initializes, so set it before any
# lazy cv2 import rather than relying on a caller-specific shell environment.
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"


EXPECTED_DMCACHE_SHA256 = (
    "9eeff8cd3e899ce000dea4fdf33a0e8b91c1819e604daa75f91a53f1dfdeba38"
)
EXPECTED_DMCACHE_SIGNATURE = (
    "g3_p0.5_bnd0.03_nrm0.5_pcNone_pcn1_fsNone_fst0.02_reNone_er0"
)
EXPECTED_MODEL_CACHE_SHA256 = (
    "7b569a5f5d87028edca9067132cc30a76f14e4950d7d9985410b2c4575954413"
)
ROUNDTRIP_RELATIVE_ERROR_LIMIT = 1e-6
INPUT_IDENTITY_CONTRACT_SCHEMA = contract.INPUT_CONTRACT_SCHEMA_VERSION
ORDERED_NAMES_SHA256_ALGORITHM = (
    "SHA-256 of ordered UTF-8 frame names, each followed by one LF byte"
)
IMAGE_ROOT_MANIFEST_SHA256_ALGORITHM = (
    "SHA-256 in dmcache.frame_order of UTF-8 "
    "name\\tsha256\\tsize_bytes\\n records"
)
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
    "source_model_cache_sha256": EXPECTED_MODEL_CACHE_SHA256,
    "source_arkit_manifest_sha256": (
        "a0d96d9c7ba0ffa78329345573e52be789e08f79ecd61f21bfd48fd76ba1f350"
    ),
}

ExrWriter = Callable[..., Mapping[str, object] | None]
ExrReader = Callable[[Path], np.ndarray]


def _not_equivalent() -> None:
    raise contract.RouteInputNotEquivalent(contract.ROUTE_INPUT_NOT_EQUIVALENT)


def _new_absolute_output_path(output: Path | str) -> Path:
    """Validate output identity without dereferencing a final symlink."""
    raw = Path(output)
    if not raw.is_absolute():
        raise ValueError("output must be an absolute path")
    if ".." in raw.parts:
        raise ValueError("output must not contain '..' path components")
    normalized = Path(os.path.normpath(os.fspath(raw)))
    if os.path.lexists(normalized):
        raise FileExistsError(f"output must not already exist: {normalized}")
    return normalized


def _create_new_output_directory(output: Path) -> None:
    """Create missing parents and output without traversing symlink components."""
    if not output.is_absolute() or not output.name:
        raise ValueError("output must be an absolute non-root path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("safe no-follow directory creation is unavailable")

    open_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        open_flags |= os.O_CLOEXEC
    directory_fd = os.open(output.anchor, open_flags)
    try:
        for component in output.parts[1:-1]:
            try:
                child_fd = os.open(component, open_flags, dir_fd=directory_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=directory_fd)
                except FileExistsError:
                    # A concurrent creator is acceptable only if the no-follow
                    # open below proves it created a real directory.
                    pass
                child_fd = os.open(component, open_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd

        try:
            os.mkdir(output.name, mode=0o755, dir_fd=directory_fd)
        except FileExistsError as exc:
            raise FileExistsError(
                f"output must not already exist: {output}"
            ) from exc
        output_fd = os.open(output.name, open_flags, dir_fd=directory_fd)
        os.close(output_fd)
    finally:
        os.close(directory_fd)


def ordered_names_sha256(names: Sequence[str]) -> str:
    """Compatibility name; the shared contract module owns the encoding."""
    return contract.ordered_frame_names_sha256(names)


def image_root_manifest_sha256(
    frame_order: Sequence[str], by_name: Mapping[str, object]
) -> str:
    """Compatibility name; the shared contract module owns the encoding."""
    return contract.image_identity_manifest_sha256(frame_order, by_name)


def load_input_identity_contract(path: Path | str) -> dict[str, object]:
    """Compatibility name delegating schema and duplicate-key checks to SSOT."""
    payload, _sha256 = contract.load_input_contract(path)
    return dict(payload)


def image_paths_from_root(
    image_root: Path | str, frame_names: Sequence[str]
) -> dict[str, Path]:
    root = Path(image_root).resolve()
    if not root.is_dir():
        _not_equivalent()
    mapping = {name: (root / name).resolve() for name in frame_names}
    if any(not path.is_file() for path in mapping.values()):
        _not_equivalent()
    return mapping


def image_paths_from_manifest(
    manifest_path: Path | str,
    frame_names: Sequence[str],
    *,
    image_root: Path | str,
) -> dict[str, Path]:
    manifest = Path(manifest_path).resolve()
    root = Path(image_root).resolve()
    if not root.is_dir():
        _not_equivalent()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _not_equivalent()

    records: object
    if isinstance(payload, dict) and "frames" in payload:
        records = payload["frames"]
    elif isinstance(payload, list):
        records = payload
    else:
        _not_equivalent()
    if not isinstance(records, list):
        _not_equivalent()

    discovered: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict):
            _not_equivalent()
        raw_path = record.get("jpegPath", record.get("path"))
        if not isinstance(raw_path, str) or not raw_path:
            _not_equivalent()
        relative_or_absolute = Path(raw_path)
        name = relative_or_absolute.name
        if name in discovered:
            _not_equivalent()
        if relative_or_absolute.is_absolute():
            candidates = [relative_or_absolute.resolve()]
        else:
            if ".." in relative_or_absolute.parts:
                _not_equivalent()
            # Diagnostics manifests are commonly stored far away from their
            # capture.  jpegPath is capture-relative (for example
            # photos_highres/x.jpg), never manifest-directory-relative.  Also
            # accept an explicitly supplied photo directory by basename.
            candidates = [
                (root / relative_or_absolute).resolve(),
                (root / relative_or_absolute.name).resolve(),
            ]
        existing: list[Path] = []
        for candidate in candidates:
            if candidate.is_file() and candidate not in existing:
                existing.append(candidate)
        if len(existing) != 1:
            _not_equivalent()
        discovered[name] = existing[0]

    mapping: dict[str, Path] = {}
    for name in frame_names:
        path = discovered.get(name)
        if path is None or not path.is_file():
            _not_equivalent()
        mapping[name] = path
    return mapping


def _max_float32_relative_error(expected: np.ndarray, actual: np.ndarray) -> float:
    left = np.asarray(expected, dtype=np.float32)
    right = np.asarray(actual, dtype=np.float32)
    if left.shape != right.shape or not np.all(np.isfinite(right)):
        raise RuntimeError("EXR read-back shape/value mismatch")
    denominator = np.maximum(np.abs(left).astype(np.float64), np.finfo(np.float32).tiny)
    return float(
        np.max(np.abs(right.astype(np.float64) - left.astype(np.float64)) / denominator)
    )


def read_float_exr(path: Path) -> np.ndarray:
    """Read a one-channel float32 EXR through the Python 3.11 OpenCV backend."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "EXR backend unavailable: cv2 is required for serialized read-back"
        ) from exc
    try:
        pixels = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    except cv2.error as exc:
        raise RuntimeError(
            "OpenCV EXR read-back failed; OPENCV_IO_ENABLE_OPENEXR=1 is required"
        ) from exc
    if pixels is None:
        raise RuntimeError(f"OpenCV could not read serialized EXR: {path}")
    data = np.asarray(pixels)
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[:, :, 0]
    if data.ndim != 2 or data.dtype != np.float32 or not np.all(np.isfinite(data)):
        raise RuntimeError("serialized EXR must read back as finite one-channel float32")
    return np.ascontiguousarray(data)


@lru_cache(maxsize=1)
def probe_opencv_exr_backend() -> dict[str, object]:
    """Prove the Python 3.11 OpenCV codec can write/read float32 EXR.

    OpenCV remains unsuitable as the production writer because its API cannot
    emit the typed AliceVision attributes.  This probe distinguishes that
    metadata limitation from a missing/disabled OpenEXR codec.
    """
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("EXR backend unavailable: cv2 is not installed") from exc
    expected = np.asarray([[0.0, 1.25], [-1.0, 512.5]], dtype=np.float32)
    with tempfile.TemporaryDirectory(prefix="b0-opencv-exr-probe-") as tmp:
        path = Path(tmp) / "probe.exr"
        try:
            written = cv2.imwrite(
                str(path),
                expected,
                [
                    cv2.IMWRITE_EXR_TYPE,
                    cv2.IMWRITE_EXR_TYPE_FLOAT,
                    cv2.IMWRITE_EXR_COMPRESSION,
                    cv2.IMWRITE_EXR_COMPRESSION_ZIP,
                ],
            )
        except cv2.error as exc:
            raise RuntimeError(
                "OpenCV float32 EXR writer probe failed; "
                "OPENCV_IO_ENABLE_OPENEXR=1 is required"
            ) from exc
        if not written:
            raise RuntimeError("OpenCV float32 EXR writer probe returned false")
        restored = read_float_exr(path)
        relative_error = _max_float32_relative_error(expected, restored)
        if relative_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT:
            raise RuntimeError("OpenCV float32 EXR probe exceeded tolerance")
    return {
        "version": str(getattr(cv2, "__version__", "unknown")),
        "environment": os.environ["OPENCV_IO_ENABLE_OPENEXR"],
        "float32_writer_verified": True,
        "float32_readback_verified": True,
        "max_relative_error": relative_error,
    }


def write_typed_exr(
    path: Path, pixels: np.ndarray, *, depth_values: int
) -> dict[str, object]:
    """Write and read back an AliceVision-compatible one-channel float32 EXR.

    OpenCV's EXR codec is deliberately used for the independent numeric
    read-back, but not as the writer: cv2.imwrite cannot attach the typed
    AliceVision metadata required by meshing.  The installed OpenEXR 3.x writer
    supplies those attributes without requiring Python 3.14/OpenImageIO.
    """
    try:
        import OpenEXR
    except ImportError as exc:
        raise RuntimeError(
            "EXR backend unavailable: OpenEXR 3.x is required for AliceVision metadata"
        ) from exc

    opencv_backend = probe_opencv_exr_backend()
    data = np.asarray(pixels, dtype=np.float32)
    if data.ndim != 2 or not np.all(np.isfinite(data)):
        raise ValueError("EXR pixels must be a finite HxW array")
    if not isinstance(depth_values, int) or not 0 <= depth_values <= data.size:
        raise ValueError("depth_values must be an integer within the image extent")
    path = Path(path)
    header = {
        "compression": OpenEXR.ZIP_COMPRESSION,
        "AliceVision:downscale": 1,
        "AliceVision:nbDepthValues": depth_values,
    }
    try:
        OpenEXR.File(header, {"Y": np.ascontiguousarray(data)}).write(str(path))
    except Exception as exc:
        raise RuntimeError(f"OpenEXR could not write {path}") from exc
    if not path.is_file():
        raise RuntimeError(f"OpenEXR did not create {path}")

    try:
        serialized_header = OpenEXR.File(
            str(path), separate_channels=True
        ).header()
    except Exception as exc:
        raise RuntimeError(f"OpenEXR could not inspect {path}") from exc
    if (
        serialized_header.get("AliceVision:downscale") != 1
        or serialized_header.get("AliceVision:nbDepthValues") != depth_values
    ):
        raise RuntimeError("serialized EXR lost required AliceVision metadata")

    restored = read_float_exr(path)
    serialization_error = _max_float32_relative_error(data, restored)
    if serialization_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT:
        raise RuntimeError("serialized EXR float32 round-trip exceeded tolerance")
    return {
        "writer_backend": "OpenEXR.File",
        "writer_version": str(getattr(OpenEXR, "__version__", "unknown")),
        "readback_backend": "cv2.imread",
        "opencv_openexr_environment": os.environ["OPENCV_IO_ENABLE_OPENEXR"],
        "opencv_backend": opencv_backend,
        "writer_selection_reason": (
            "OpenCV_cannot_emit_typed_AliceVision_attributes"
        ),
        "max_float32_serialization_relative_error": serialization_error,
        "sha256": contract.sha256_file(path),
    }


def _as_string(value: float) -> str:
    return repr(float(value))


def _serialize_rotation_for_alicevision(rotation_w2c: np.ndarray) -> list[str]:
    """Serialize Eigen Mat3 in the column-major sequence AliceVision reads."""
    rotation = np.asarray(rotation_w2c, dtype=np.float64)
    if rotation.shape != (3, 3) or not np.all(np.isfinite(rotation)):
        _not_equivalent()
    return [_as_string(value) for value in rotation.reshape(-1, order="F")]


def _build_scene_entry(
    *,
    view_id: int,
    image_path: Path,
    width: int,
    height: int,
    K: np.ndarray,
    w2c: np.ndarray,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    intrinsics = np.asarray(K)
    pose = np.asarray(w2c)
    if intrinsics.shape != (3, 3) or pose.shape not in {(3, 4), (4, 4)}:
        _not_equivalent()
    if not np.all(np.isfinite(intrinsics)) or not np.all(np.isfinite(pose)):
        _not_equivalent()
    rotation = pose[:3, :3].astype(np.float64)
    translation = pose[:3, 3].astype(np.float64)
    center = -(rotation.T @ translation)
    fx = float(intrinsics[0, 0])
    fy = float(intrinsics[1, 1])
    cx = float(intrinsics[0, 2])
    cy = float(intrinsics[1, 2])
    if fx <= 0.0 or fy <= 0.0:
        _not_equivalent()

    identifier = str(view_id)
    view = {
        "viewId": identifier,
        "poseId": identifier,
        "frameId": identifier,
        "intrinsicId": identifier,
        "resectionId": "4294967295",
        "path": str(image_path.resolve()),
        "width": str(width),
        "height": str(height),
        "metadata": {},
    }
    intrinsic = {
        "intrinsicId": identifier,
        "width": str(width),
        "height": str(height),
        "sensorWidth": _as_string(float(width)),
        "sensorHeight": _as_string(float(height)),
        "serialNumber": "pocketworld-b0-frozen",
        "type": "pinhole",
        "initializationMode": "calibrated",
        "initialFocalLength": _as_string(fx),
        "focalLength": _as_string(fx),
        "pixelRatio": _as_string(fy / fx),
        "pixelRatioLocked": "true",
        # AliceVision v1.2.9 expects offset from the image center, not absolute cx/cy.
        "principalPoint": [_as_string(cx - width / 2.0), _as_string(cy - height / 2.0)],
        "distortionInitializationMode": "none",
        "distortionType": "none",
        "undistortionType": "none",
        "distortionParams": [],
        "undistortionParams": [],
        "undistortionOffset": ["0.0", "0.0"],
        "locked": "true",
    }
    pose_entry = {
        "poseId": identifier,
        "pose": {
            "transform": {
                "rotation": _serialize_rotation_for_alicevision(rotation),
                "center": [_as_string(value) for value in center],
            },
            "locked": "1",
        },
    }
    return view, intrinsic, pose_entry


def _validate_route_bindings(
    *,
    payload: Mapping[str, object],
    split_id: str,
    dmcache_sha256: str,
    dmcache_signature: str,
    depth_all: np.ndarray,
    dm_frames: Sequence[str],
    model_cache_sha256: str,
    model_names: Sequence[str],
    frame_list_path: Path,
    requested: Sequence[str],
    actual_images: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    # Schema, coordinate-frame acceptance, scale, split partitioning, model
    # universe, image manifest encoding, and duplicate-key handling are owned
    # exclusively by b0_input_contract.py.  This adapter only binds those
    # already-validated identities to the files it is about to serialize.
    frozen = contract.validate_input_contract(payload)
    selected_split = contract.select_input_contract_split(frozen, split_id)
    policy = frozen["transductive_policy"]
    if policy["route_allowed"] is not True or selected_split.get(
        "route_allowed", True
    ) is not True:
        _not_equivalent()

    dmcache = frozen["dmcache"]
    depth_contract = dmcache["depth"]
    if (
        dmcache["sha256"] != dmcache_sha256
        or dmcache["signature"] != dmcache_signature
        or depth_contract["shape"] != list(np.asarray(depth_all).shape)
        or depth_contract["dtype"] != str(np.asarray(depth_all).dtype)
        or dmcache["frame_order"] != list(dm_frames)
    ):
        _not_equivalent()

    model_cache = frozen["model_cache"]
    if (
        model_cache["sha256"] != model_cache_sha256
        or model_cache["frame_order"] != list(model_names)
    ):
        _not_equivalent()

    reconstruction = selected_split["reconstruction"]
    heldout = selected_split["heldout"]
    if (
        reconstruction["frames"] != list(requested)
        or reconstruction["file_sha256"] != contract.sha256_file(frame_list_path)
    ):
        _not_equivalent()

    images = frozen["images"]
    by_name = images["by_name"]
    if set(actual_images) != set(dm_frames):
        _not_equivalent()
    for name in dm_frames:
        frozen_image = by_name.get(name)
        actual_image = actual_images.get(name)
        if (
            not isinstance(frozen_image, Mapping)
            or not isinstance(actual_image, Mapping)
            or frozen_image.get("sha256") != actual_image.get("sha256")
            or frozen_image.get("size_bytes") != actual_image.get("size_bytes")
        ):
            _not_equivalent()

    return {
        "dataset_id": frozen["dataset_id"],
        "coordinate_frame": frozen["coordinate_frame"],
        "metres_per_model_unit": float(frozen["metres_per_model_unit"]),
        "transductive_policy": dict(policy),
        "split_id": split_id,
        "dmcache_frame_order_sha256": dmcache["frame_order_sha256"],
        "model_cache_frame_order_sha256": model_cache["frame_order_sha256"],
        "reconstruction_file_sha256": reconstruction["file_sha256"],
        "reconstruction_semantic_sha256": reconstruction["semantic_sha256"],
        "heldout_file_sha256": heldout["file_sha256"],
        "heldout_semantic_sha256": heldout["semantic_sha256"],
        "image_root_manifest_sha256": images["root_manifest_sha256"],
    }


def export_alicevision(
    *,
    dmcache_path: Path | str,
    model_cache_path: Path | str,
    frame_list_path: Path | str,
    image_paths: Mapping[str, Path],
    output: Path | str,
    expected_dmcache_sha256: str | None = None,
    expected_signature: str | None = None,
    expected_model_cache_sha256: str | None = None,
    exr_writer: ExrWriter = write_typed_exr,
    exr_reader: ExrReader | None = None,
    image_root: Path | str | None = None,
    image_manifest_path: Path | str | None = None,
    universe_image_paths: Mapping[str, Path] | None = None,
    input_contract_path: Path | str | None = None,
    split_id: str | None = None,
) -> dict[str, object]:
    """Validate all route inputs, then create a brand-new AliceVision directory."""
    output_path = _new_absolute_output_path(output)

    dmcache = Path(dmcache_path).resolve()
    model_cache = Path(model_cache_path).resolve()
    frame_list = Path(frame_list_path).resolve()
    if not dmcache.is_file() or not model_cache.is_file() or not frame_list.is_file():
        _not_equivalent()

    if (input_contract_path is None) != (split_id is None):
        _not_equivalent()
    frozen_contract: dict[str, object] | None = None
    normalized_contract_path: Path | None = None
    input_contract_sha256: str | None = None
    if input_contract_path is not None:
        if not isinstance(split_id, str) or not split_id:
            _not_equivalent()
        normalized_contract_path = Path(input_contract_path).resolve()
        loaded_contract, input_contract_sha256 = contract.load_input_contract(
            normalized_contract_path
        )
        frozen_contract = dict(loaded_contract)

    dmcache_sha256 = contract.sha256_file(dmcache)
    model_cache_sha256 = contract.sha256_file(model_cache)
    requested = contract.parse_frame_list(frame_list)

    try:
        with np.load(dmcache, allow_pickle=False) as depth_archive:
            dm_frames_raw = depth_archive["frames"]
            depth_all = depth_archive["dm"]
            signature_raw = depth_archive["sig"]
        with np.load(model_cache, allow_pickle=False) as model_archive:
            model_names_raw = model_archive["names"]
            K_all = model_archive["K"]
            w2c_all = model_archive["w2c"]
    except (OSError, ValueError, KeyError):
        _not_equivalent()

    dm_frames = [str(name) for name in dm_frames_raw.tolist()]
    model_names = [str(name) for name in model_names_raw.tolist()]
    if np.asarray(signature_raw).shape != ():
        _not_equivalent()
    dmcache_signature = str(np.asarray(signature_raw).item())
    if (
        np.asarray(depth_all).ndim != 3
        or np.asarray(depth_all).dtype != np.float32
        or len(dm_frames) != np.asarray(depth_all).shape[0]
        or np.asarray(K_all).shape != (len(model_names), 3, 3)
        or np.asarray(K_all).dtype.kind != "f"
        or np.asarray(w2c_all).shape not in {
            (len(model_names), 3, 4),
            (len(model_names), 4, 4),
        }
        or np.asarray(w2c_all).dtype.kind != "f"
    ):
        _not_equivalent()

    depth_indices = contract.validate_ordered_subsequence(requested, dm_frames)
    model_indices = contract.validate_ordered_subsequence(requested, model_names)
    # Image resolution/path are part of the executable scene, so prove the
    # caller supplied exactly the requested key set and existing files.
    if set(image_paths) != set(requested):
        _not_equivalent()
    normalized_images = {name: Path(image_paths[name]).resolve() for name in requested}
    if any(not path.is_file() for path in normalized_images.values()):
        _not_equivalent()
    if frozen_contract is not None:
        if universe_image_paths is None or set(universe_image_paths) != set(dm_frames):
            _not_equivalent()
        normalized_universe_images = {
            name: Path(universe_image_paths[name]).resolve() for name in dm_frames
        }
        if (
            any(not path.is_file() for path in normalized_universe_images.values())
            or any(
                normalized_images[name] != normalized_universe_images[name]
                for name in requested
            )
        ):
            _not_equivalent()
    else:
        normalized_universe_images = normalized_images
    normalized_image_root: Path | None = None
    if image_root is not None:
        normalized_image_root = Path(image_root).resolve()
        if not normalized_image_root.is_dir():
            _not_equivalent()
    normalized_image_manifest: Path | None = None
    if image_manifest_path is not None:
        normalized_image_manifest = Path(image_manifest_path).resolve()
        if not normalized_image_manifest.is_file():
            _not_equivalent()
    universe_image_identities = {
        name: {
            "sha256": contract.sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in normalized_universe_images.items()
    }
    image_source_frames = [
        {
            "frame": name,
            "path": str(normalized_images[name]),
            **universe_image_identities[name],
        }
        for name in requested
    ]
    image_source_manifest_sha256 = hashlib.sha256(
        json.dumps(
            image_source_frames,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    identity_evidence: dict[str, object]
    if frozen_contract is not None:
        identity_evidence = _validate_route_bindings(
            payload=frozen_contract,
            split_id=str(split_id),
            dmcache_sha256=dmcache_sha256,
            dmcache_signature=dmcache_signature,
            depth_all=np.asarray(depth_all),
            dm_frames=dm_frames,
            model_cache_sha256=model_cache_sha256,
            model_names=model_names,
            frame_list_path=frame_list,
            requested=requested,
            actual_images=universe_image_identities,
        )
        # Explicit function-level expectations may only add an identical check;
        # they can never override the frozen contract.
        if (
            expected_dmcache_sha256 not in {None, dmcache_sha256}
            or expected_signature not in {None, dmcache_signature}
            or expected_model_cache_sha256 not in {None, model_cache_sha256}
        ):
            _not_equivalent()
    else:
        if (
            expected_dmcache_sha256 is None
            or expected_signature is None
            or expected_model_cache_sha256 is None
            or dmcache_sha256 != expected_dmcache_sha256
            or dmcache_signature != expected_signature
            or model_cache_sha256 != expected_model_cache_sha256
        ):
            _not_equivalent()
        identity_evidence = {
            "dataset_id": "explicit-function-expectations",
            "coordinate_frame": "raw_lapa_model",
            "metres_per_model_unit": float(FROZEN_SIM3["scale"]),
            "transductive_policy": None,
            "split_id": None,
        }

    height, width = np.asarray(depth_all).shape[1:]
    prepared: list[dict[str, object]] = []
    per_frame_hashes: list[str] = []
    max_roundtrip_error = 0.0
    for order_index, name in enumerate(requested):
        depth_z = np.asarray(depth_all[depth_indices[order_index]])
        K = np.asarray(K_all[model_indices[order_index]])
        w2c = np.asarray(w2c_all[model_indices[order_index]])
        mask = np.isfinite(depth_z) & (depth_z > 0)
        semantic_hash = contract.canonical_frame_semantic_sha256(
            name, mask, depth_z, K, w2c
        )
        ray = contract.camera_z_to_euclidean_ray(depth_z, K)
        restored = contract.euclidean_ray_to_camera_z(ray, K)
        roundtrip_error = contract.max_relative_roundtrip_error(depth_z, restored, mask)
        if not np.isfinite(roundtrip_error) or roundtrip_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT:
            _not_equivalent()
        max_roundtrip_error = max(max_roundtrip_error, roundtrip_error)
        prepared.append(
            {
                "name": name,
                "dmcache_index": depth_indices[order_index],
                "K": K,
                "w2c": w2c,
                "depth_z": depth_z,
                "mask": mask,
                "ray": ray.astype(np.float32),
                "valid_depth_count": int(np.count_nonzero(mask)),
                "semantic_hash": semantic_hash,
            }
        )
        per_frame_hashes.append(semantic_hash)

    # No filesystem mutation occurs until every identity and numeric gate passes.
    _create_new_output_directory(output_path)
    depth_directory = output_path / "depthMaps"
    depth_directory.mkdir(exist_ok=False)
    views: list[dict[str, object]] = []
    intrinsics: list[dict[str, object]] = []
    poses: list[dict[str, object]] = []
    serialized_exrs: list[dict[str, object]] = []
    max_serialized_z_roundtrip_error = 0.0
    max_serialized_float32_error = 0.0
    # An injected writer is a unit-test seam and may intentionally emit a
    # sentinel rather than an EXR.  Production uses the default real writer and
    # must always perform independent serialized read-back.  Tests of numeric
    # export can opt in with an injected reader.
    verify_serialized = exr_reader is not None or exr_writer is write_typed_exr
    resolved_exr_reader = exr_reader or read_float_exr
    for item in prepared:
        # Stable across cap50/full gates: identity follows the frozen global
        # dmcache slot, never the selected subset position.
        view_id = 1000 + int(item["dmcache_index"])
        ray = np.asarray(item["ray"], dtype=np.float32)
        similarity = np.full((height, width), -1.0, dtype=np.float32)
        valid_depth_count = int(item["valid_depth_count"])
        depth_path = depth_directory / f"{view_id}_depthMap.exr"
        sim_path = depth_directory / f"{view_id}_simMap.exr"
        depth_write_result = exr_writer(
            depth_path,
            ray,
            depth_values=valid_depth_count,
        )
        sim_write_result = exr_writer(
            sim_path,
            similarity,
            depth_values=valid_depth_count,
        )
        depth_float_error: float | None = None
        sim_float_error: float | None = None
        if verify_serialized:
            serialized_ray = np.asarray(resolved_exr_reader(depth_path))
            serialized_similarity = np.asarray(resolved_exr_reader(sim_path))
            if (
                serialized_ray.dtype != np.float32
                or serialized_similarity.dtype != np.float32
                or serialized_ray.shape != ray.shape
                or serialized_similarity.shape != similarity.shape
                or not np.all(np.isfinite(serialized_ray))
                or not np.all(np.isfinite(serialized_similarity))
            ):
                _not_equivalent()
            depth_float_error = _max_float32_relative_error(ray, serialized_ray)
            sim_float_error = _max_float32_relative_error(
                similarity, serialized_similarity
            )
            if (
                depth_float_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT
                or sim_float_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT
            ):
                _not_equivalent()
            serialized_restored_z = contract.euclidean_ray_to_camera_z(
                serialized_ray, np.asarray(item["K"])
            )
            serialized_z_error = contract.max_relative_roundtrip_error(
                np.asarray(item["depth_z"]),
                serialized_restored_z,
                np.asarray(item["mask"]),
            )
            if (
                not np.isfinite(serialized_z_error)
                or serialized_z_error > ROUNDTRIP_RELATIVE_ERROR_LIMIT
            ):
                _not_equivalent()
            max_serialized_z_roundtrip_error = max(
                max_serialized_z_roundtrip_error, serialized_z_error
            )
            max_serialized_float32_error = max(
                max_serialized_float32_error,
                depth_float_error,
                sim_float_error,
            )
        for kind, path, result, error in (
            ("depth", depth_path, depth_write_result, depth_float_error),
            ("similarity", sim_path, sim_write_result, sim_float_error),
        ):
            serialized_exrs.append(
                {
                    "view_id": view_id,
                    "kind": kind,
                    "path": str(path.resolve()),
                    "sha256": contract.sha256_file(path),
                    "max_float32_serialization_relative_error": error,
                    "backend": (
                        dict(result)
                        if isinstance(result, Mapping)
                        else {
                            "writer_backend": "injected",
                            "readback_backend": (
                                "injected" if verify_serialized else "not_verified"
                            ),
                        }
                    ),
                }
            )
        view, intrinsic, pose = _build_scene_entry(
            view_id=view_id,
            image_path=normalized_images[str(item["name"])],
            width=width,
            height=height,
            K=np.asarray(item["K"]),
            w2c=np.asarray(item["w2c"]),
        )
        views.append(view)
        intrinsics.append(intrinsic)
        poses.append(pose)

    scene = {
        "version": ["1", "2", "9"],
        "views": views,
        "intrinsics": intrinsics,
        "poses": poses,
    }
    (output_path / "scene.sfm").write_text(
        json.dumps(scene, indent=2) + "\n", encoding="utf-8"
    )
    provenance: dict[str, object] = {
        "schema": "pocketworld-b0-alicevision-export-v1",
        "dataset_id": identity_evidence["dataset_id"],
        "coordinate_frame": identity_evidence["coordinate_frame"],
        "metres_per_model_unit": identity_evidence["metres_per_model_unit"],
        "transductive_policy": identity_evidence["transductive_policy"],
        "depth_source_encoding": "camera_z_float32",
        "depth_export_encoding": "euclidean_ray_float32",
        "depth_formula": "d_ray=d_z*sqrt(((u-cx)/fx)^2+((v-cy)/fy)^2+1)",
        "similarity_map": "constant_-1.0_neutral",
        "confidence_filtering": "none",
        "smoothing": "none",
        "frame_count": len(requested),
        "frame_order": requested,
        "frame_list_sha256": contract.sha256_file(frame_list),
        "dmcache_path": str(dmcache),
        "dmcache_sha256": dmcache_sha256,
        "dmcache_signature": dmcache_signature,
        "model_cache_path": str(model_cache),
        "model_cache_sha256": model_cache_sha256,
        "image_source": {
            "root_path": (
                str(normalized_image_root)
                if normalized_image_root is not None
                else None
            ),
            "diagnostics_manifest_path": (
                str(normalized_image_manifest)
                if normalized_image_manifest is not None
                else None
            ),
            "diagnostics_manifest_sha256": (
                contract.sha256_file(normalized_image_manifest)
                if normalized_image_manifest is not None
                else None
            ),
            "frames": image_source_frames,
            "ordered_manifest_sha256": image_source_manifest_sha256,
            "validated_universe_frame_count": (
                len(normalized_universe_images)
                if frozen_contract is not None
                else None
            ),
            "validated_universe_root_manifest_sha256": identity_evidence.get(
                "image_root_manifest_sha256"
            ),
        },
        "per_frame_semantic_sha256": per_frame_hashes,
        "semantic_manifest_sha256": contract.semantic_manifest_sha256(
            per_frame_hashes
        ),
        "semantic_hash_schema": {
            "version": contract.SEMANTIC_HASH_VERSION,
            "components_in_order": [
                "exact frame basename UTF-8 bytes",
                "mask = isfinite(dm) & (dm > 0)",
                "camera-Z depth in frozen dm dtype without conversion",
                "name-joined K in frozen model-cache dtype",
                "name-joined w2c in frozen contract coordinate-frame dtype",
            ],
            "array_encoding": (
                "length-prefixed field tag, dtype.str, shape, and raw C-order bytes"
            ),
            "manifest_encoding": (
                "ordered length-prefixed binary per-frame SHA-256 digests"
            ),
        },
        "input_equivalence_contract": {
            "status": "VALIDATED_FOR_FUSECUT_ARM",
            "semantic_manifest_sha256": contract.semantic_manifest_sha256(
                per_frame_hashes
            ),
            "semantic_hash_version": contract.SEMANTIC_HASH_VERSION,
            "depth_semantics": "camera_z",
            "mask_semantics": "isfinite(dm) & (dm > 0)",
            "ordered_subset": True,
            "confidence_filtering": False,
            "smoothing": False,
            "coordinate_frame": identity_evidence["coordinate_frame"],
            "frozen_input_contract": {
                "path": (
                    str(normalized_contract_path)
                    if normalized_contract_path is not None
                    else None
                ),
                "sha256": input_contract_sha256,
                "schema_version": (
                    INPUT_IDENTITY_CONTRACT_SCHEMA
                    if frozen_contract is not None
                    else None
                ),
                "split_id": identity_evidence["split_id"],
                "validated_fields": identity_evidence,
                "hash_algorithms": {
                    "frame_order_and_split_semantic": (
                        ORDERED_NAMES_SHA256_ALGORITHM
                    ),
                    "frame_list_file_sha256": (
                        "SHA-256 of exact raw frame-list file bytes"
                    ),
                    "images_root_manifest": (
                        IMAGE_ROOT_MANIFEST_SHA256_ALGORITHM
                    ),
                },
            },
        },
        "max_z_ray_z_relative_roundtrip_error": max_roundtrip_error,
        "max_z_ray_z_relative_roundtrip_error_limit": (
            ROUNDTRIP_RELATIVE_ERROR_LIMIT
        ),
        "serialized_exr_roundtrip_verified": verify_serialized,
        "max_serialized_z_ray_z_relative_roundtrip_error": (
            max_serialized_z_roundtrip_error if verify_serialized else None
        ),
        "max_serialized_float32_relative_error": (
            max_serialized_float32_error if verify_serialized else None
        ),
        "serialized_exrs": serialized_exrs,
        "exr_runtime_contract": {
            "writer": "OpenEXR.File with typed AliceVision metadata",
            "independent_readback": "cv2.imread IMREAD_UNCHANGED",
            "opencv_openexr_environment": os.environ[
                "OPENCV_IO_ENABLE_OPENEXR"
            ],
            "relative_error_limit": ROUNDTRIP_RELATIVE_ERROR_LIMIT,
        },
        "alicevision_rotation_serialization": "column_major",
        "principal_point_encoding": "offset_from_image_center",
        "frozen_sim3_model_to_arkit": {
            **FROZEN_SIM3,
            "applied_by_adapter": False,
            "applicable": (
                identity_evidence["coordinate_frame"] == "raw_lapa_model"
            ),
            "application_stage": (
                "once_after_per_route_meshing"
                if identity_evidence["coordinate_frame"] == "raw_lapa_model"
                else (
                    "not_applicable_input_is_already_metric_arkit_cv"
                    if identity_evidence["coordinate_frame"] == "metric_arkit_cv"
                    else (
                        "not_applicable_optimized_sfm_cv_uses_contract_scale_"
                        "without_adapter_alignment"
                    )
                )
            ),
        },
    }
    provenance["frozen_input_identity_contract"] = provenance[
        "input_equivalence_contract"
    ]["frozen_input_contract"]
    if (
        normalized_contract_path is not None
        and contract.sha256_file(normalized_contract_path)
        != input_contract_sha256
    ):
        _not_equivalent()
    (output_path / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export frozen B0 camera-Z inputs for AliceVision fuseCut."
    )
    parser.add_argument("--dmcache", required=True, type=Path)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--frame-list", required=True, type=Path)
    parser.add_argument(
        "--image-root",
        required=True,
        type=Path,
        help=(
            "explicit photo directory or capture root; relative manifest "
            "jpegPath values are resolved only against this root"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="optional diagnostics manifest used to join jpegPath by basename",
    )
    parser.add_argument(
        "--input-contract",
        required=True,
        type=Path,
        help="immutable b0-input-contract-v1 JSON frozen before route output",
    )
    parser.add_argument(
        "--split-id",
        required=True,
        help="contract split whose reconstruction frames must equal --frame-list",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help=(
            "absolute brand-new output directory; missing real-directory "
            "parents are created and existing/symlink paths are rejected"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    frame_names = contract.parse_frame_list(args.frame_list)
    frozen_contract = load_input_identity_contract(args.input_contract)
    frozen_dmcache = frozen_contract.get("dmcache")
    if not isinstance(frozen_dmcache, Mapping) or not isinstance(
        frozen_dmcache.get("frame_order"), list
    ):
        _not_equivalent()
    universe_names = frozen_dmcache["frame_order"]
    if args.manifest is None:
        universe_image_paths = image_paths_from_root(
            args.image_root, universe_names
        )
    else:
        universe_image_paths = image_paths_from_manifest(
            args.manifest, universe_names, image_root=args.image_root
        )
    try:
        image_paths = {name: universe_image_paths[name] for name in frame_names}
    except (KeyError, TypeError):
        _not_equivalent()
    provenance = export_alicevision(
        dmcache_path=args.dmcache,
        model_cache_path=args.model_cache,
        frame_list_path=args.frame_list,
        image_paths=image_paths,
        universe_image_paths=universe_image_paths,
        output=args.out,
        image_root=args.image_root,
        image_manifest_path=args.manifest,
        input_contract_path=args.input_contract,
        split_id=args.split_id,
    )
    print(
        json.dumps(
            {
                "output": str(args.out.resolve()),
                "frame_count": provenance["frame_count"],
                "semantic_manifest_sha256": provenance[
                    "semantic_manifest_sha256"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
