#!/usr/bin/env python3
"""Fail-closed input identity helpers for the B0 TSDF/fuseCut comparison.

The comparison is only meaningful when both routes consume byte-identical
camera-Z observations, masks, intrinsics, and poses in one explicitly frozen
coordinate frame and frame order.  This module deliberately has no project or
third-party runtime imports beyond NumPy, so both routes can use exactly the
same implementation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

import numpy as np


ROUTE_INPUT_NOT_EQUIVALENT = "ROUTE_INPUT_NOT_EQUIVALENT"
SEMANTIC_HASH_VERSION = "b0-frame-semantic-v1"
INPUT_CONTRACT_SCHEMA_VERSION = "b0-input-contract-v1"
RAW_LAPA_METRES_PER_MODEL_UNIT = 0.21677133346045502
SUPPORTED_COORDINATE_SCALES = {
    "raw_lapa_model": RAW_LAPA_METRES_PER_MODEL_UNIT,
    "metric_arkit_cv": 1.0,
}
VARIABLE_SCALE_COORDINATE_FRAMES = {"optimized_sfm_cv"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RouteInputNotEquivalent(ValueError):
    """Raised when the two B0 routes cannot prove identical inputs."""


def _not_equivalent() -> None:
    # Keep the externally consumed diagnostic exact and stable.  More detailed
    # context belongs in the run provenance, never in the gate token.
    raise RouteInputNotEquivalent(ROUTE_INPUT_NOT_EQUIVALENT)


def sha256_stream(stream: BinaryIO, *, chunk_size: int = 1024 * 1024) -> str:
    """Return SHA-256 of bytes read from the stream's current position."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("binary stream required")
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    with Path(path).open("rb") as stream:
        return sha256_stream(stream, chunk_size=chunk_size)


def ordered_frame_names_bytes(names: Sequence[str]) -> bytes:
    """Encode an ordered frame identity exactly as the B0 contract specifies."""
    normalized = _validate_frame_names(list(names), allow_empty=True)
    return "".join(f"{name}\n" for name in normalized).encode("utf-8")


def ordered_frame_names_sha256(names: Sequence[str]) -> str:
    """Hash ordered ``name + LF`` UTF-8 records without sorting."""
    return hashlib.sha256(ordered_frame_names_bytes(names)).hexdigest()


def _validated_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _not_equivalent()
    return value


def image_identity_manifest_sha256(
    frame_order: Sequence[str], identities: Mapping[str, Mapping[str, object]]
) -> str:
    """Hash image identities in dmcache order.

    Each UTF-8 record is exactly ``name<TAB>sha256<TAB>size_bytes<LF>``.
    Neither mapping insertion order nor filesystem enumeration participates.
    """
    names = _validate_frame_names(list(frame_order))
    if not isinstance(identities, Mapping) or set(identities) != set(names):
        _not_equivalent()
    digest = hashlib.sha256()
    for name in names:
        identity = identities.get(name)
        if not isinstance(identity, Mapping):
            _not_equivalent()
        sha256 = _validated_sha256(identity.get("sha256"))
        size = identity.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            _not_equivalent()
        digest.update(f"{name}\t{sha256}\t{size}\n".encode("utf-8"))
    return digest.hexdigest()


def _require_mapping(value: object, required: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        _not_equivalent()
    return value


def _require_identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _not_equivalent()
    return value


def _require_bool(value: object) -> bool:
    if type(value) is not bool:
        _not_equivalent()
    return value


def validate_input_contract(payload: object) -> Mapping[str, Any]:
    """Validate the generic immutable B0 input-contract core.

    Extra provenance and gate fields are preserved, but none can replace or
    weaken the required core.  Expected identities come only from this
    pre-registered object; route CLIs intentionally provide no per-component
    hash override flags.
    """
    root = _require_mapping(
        payload,
        (
            "schema_version",
            "dataset_id",
            "coordinate_frame",
            "metres_per_model_unit",
            "transductive_policy",
            "dmcache",
            "model_cache",
            "splits",
            "images",
        ),
    )
    if root["schema_version"] != INPUT_CONTRACT_SCHEMA_VERSION:
        _not_equivalent()
    dataset_id = _require_identifier(root["dataset_id"])

    coordinate_frame = root["coordinate_frame"]
    if not isinstance(coordinate_frame, str):
        _not_equivalent()
    scale = root["metres_per_model_unit"]
    scale_is_finite_positive = (
        not isinstance(scale, bool)
        and isinstance(scale, (int, float))
        and math.isfinite(float(scale))
        and float(scale) > 0.0
    )
    if (
        not scale_is_finite_positive
        or (
            coordinate_frame in SUPPORTED_COORDINATE_SCALES
            and float(scale) != SUPPORTED_COORDINATE_SCALES[coordinate_frame]
        )
        or coordinate_frame
        not in set(SUPPORTED_COORDINATE_SCALES) | VARIABLE_SCALE_COORDINATE_FRAMES
    ):
        _not_equivalent()

    policy = _require_mapping(
        root["transductive_policy"],
        ("present", "route_allowed", "quality_scoring_forbidden"),
    )
    for key in ("present", "route_allowed", "quality_scoring_forbidden"):
        _require_bool(policy[key])
    if "warning" in policy and (
        not isinstance(policy["warning"], str) or not policy["warning"]
    ):
        _not_equivalent()
    if "reason" in policy and (
        not isinstance(policy["reason"], str) or not policy["reason"]
    ):
        _not_equivalent()
    if "forbidden_claims" in policy and (
        not isinstance(policy["forbidden_claims"], list)
        or any(
            not isinstance(value, str) or not value
            for value in policy["forbidden_claims"]
        )
    ):
        _not_equivalent()

    dmcache = _require_mapping(
        root["dmcache"],
        (
            "sha256",
            "signature",
            "depth",
            "frame_order",
            "frame_order_sha256",
        ),
    )
    _validated_sha256(dmcache["sha256"])
    if not isinstance(dmcache["signature"], str) or not dmcache["signature"]:
        _not_equivalent()
    dm_frames = _validate_frame_names(dmcache["frame_order"])
    if dmcache["frame_order_sha256"] != ordered_frame_names_sha256(dm_frames):
        _not_equivalent()
    depth = _require_mapping(dmcache["depth"], ("shape", "dtype"))
    shape = depth["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) != 3
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in shape
        )
        or shape[0] != len(dm_frames)
        or depth["dtype"] != "float32"
    ):
        _not_equivalent()

    model = _require_mapping(
        root["model_cache"], ("sha256", "frame_order", "frame_order_sha256")
    )
    _validated_sha256(model["sha256"])
    model_frames = _validate_frame_names(model["frame_order"])
    if (
        model["frame_order_sha256"] != ordered_frame_names_sha256(model_frames)
        or len(model_frames) != len(dm_frames)
        or set(model_frames) != set(dm_frames)
    ):
        _not_equivalent()

    # The real device cap50 capture is distinguishable by its tap-image
    # basenames.  Never let the historical cell_* spatial-100 fallback acquire
    # a cap50 dataset identity merely by changing a JSON label.
    if "cap50" in dataset_id.lower() and any(
        "_tap-" not in name for name in dm_frames
    ):
        _not_equivalent()

    splits = root["splits"]
    if not isinstance(splits, Mapping) or not splits:
        _not_equivalent()
    universe = set(dm_frames)
    for raw_split_id, raw_split in splits.items():
        _require_identifier(raw_split_id)
        split = _require_mapping(raw_split, ("reconstruction", "heldout"))
        for optional_gate in ("route_allowed", "quality_scoring_forbidden"):
            if optional_gate in split:
                _require_bool(split[optional_gate])
        if "dataset_id" in split and split["dataset_id"] != dataset_id:
            _not_equivalent()
        quality_scoring_forbidden = bool(
            policy["quality_scoring_forbidden"]
            or split.get("quality_scoring_forbidden", False)
        )
        roles: dict[str, list[str]] = {}
        for role_name in ("reconstruction", "heldout"):
            role = _require_mapping(
                split[role_name], ("frames", "file_sha256", "semantic_sha256")
            )
            names = _validate_frame_names(
                role["frames"],
                allow_empty=(
                    role_name == "heldout" and quality_scoring_forbidden
                ),
            )
            semantic = ordered_frame_names_sha256(names)
            _validated_sha256(role["file_sha256"])
            if role["semantic_sha256"] != semantic:
                _not_equivalent()
            _validated_sha256(role["semantic_sha256"])
            roles[role_name] = names
        reconstruction_set = set(roles["reconstruction"])
        heldout_set = set(roles["heldout"])
        if (
            reconstruction_set & heldout_set
            or reconstruction_set | heldout_set != universe
        ):
            _not_equivalent()

    images = _require_mapping(root["images"], ("root_manifest_sha256", "by_name"))
    by_name = images["by_name"]
    if not isinstance(by_name, Mapping):
        _not_equivalent()
    expected_image_manifest = image_identity_manifest_sha256(dm_frames, by_name)
    if images["root_manifest_sha256"] != expected_image_manifest:
        _not_equivalent()
    _validated_sha256(images["root_manifest_sha256"])
    return root


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _not_equivalent()
        result[key] = value
    return result


def load_input_contract(path: Path | str) -> tuple[Mapping[str, Any], str]:
    """Read, hash, and validate an immutable generic input-contract JSON file."""
    source = Path(path)
    try:
        raw = source.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except RouteInputNotEquivalent:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        _not_equivalent()
    return validate_input_contract(payload), hashlib.sha256(raw).hexdigest()


def select_input_contract_split(
    payload: Mapping[str, Any], split_id: str
) -> Mapping[str, Any]:
    """Return one explicitly named route/evaluation split, fail closed."""
    validate_input_contract(payload)
    identifier = _require_identifier(split_id)
    splits = payload["splits"]
    if identifier not in splits:
        _not_equivalent()
    return splits[identifier]


def _validate_frame_names(values: object, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(values, list) or (not values and not allow_empty):
        _not_equivalent()
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            _not_equivalent()
        # Frame identity is a cache/model basename.  Reject normalization and
        # path aliasing so two routes cannot silently resolve different files.
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
            _not_equivalent()
        seen.add(value)
        result.append(value)
    return result


def parse_frame_list(path: Path | str) -> list[str]:
    """Parse a strict JSON array/object or one-name-per-line frame list.

    JSON objects must use ``reconstruction_frames``.  Text files allow blank
    lines and ``#`` comments, but otherwise preserve the exact listed order.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        _not_equivalent()
    stripped = text.lstrip()
    try:
        if source.suffix.lower() == ".json" or stripped.startswith(("[", "{")):
            payload = json.loads(text)
            if isinstance(payload, dict):
                if set(payload) != {"reconstruction_frames"}:
                    _not_equivalent()
                payload = payload["reconstruction_frames"]
            return _validate_frame_names(payload)
        values = [
            line
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return _validate_frame_names(values)
    except (json.JSONDecodeError, TypeError, ValueError):
        _not_equivalent()
    raise AssertionError("unreachable")


def validate_ordered_subsequence(
    requested: Sequence[str], available: Sequence[str]
) -> list[int]:
    """Validate an ordered selection and return source indices in that order.

    The frozen experiment order is the order in ``requested``.  It need not be
    monotonic in the cache because the pre-registered cap50 ordering is spatial,
    while the cache ordering is internal.  Every name must nevertheless appear
    exactly once in each source, and requested names may not repeat.

    The historical function name is kept because the B0 scripts share this API.
    """
    try:
        requested_list = _validate_frame_names(list(requested))
        available_list = _validate_frame_names(list(available))
    except RouteInputNotEquivalent:
        raise
    index = {name: i for i, name in enumerate(available_list)}
    if len(index) != len(available_list):
        _not_equivalent()
    if any(name not in index for name in requested_list):
        _not_equivalent()
    return [index[name] for name in requested_list]


def _update_field(digest: "hashlib._Hash", tag: str, payload: bytes) -> None:
    tag_bytes = tag.encode("utf-8")
    digest.update(struct.pack(">I", len(tag_bytes)))
    digest.update(tag_bytes)
    digest.update(struct.pack(">Q", len(payload)))
    digest.update(payload)


def _update_array(digest: "hashlib._Hash", tag: str, value: np.ndarray) -> None:
    array = np.asarray(value)
    contiguous = np.ascontiguousarray(array)
    _update_field(digest, f"{tag}.dtype", array.dtype.str.encode("ascii"))
    _update_field(
        digest,
        f"{tag}.shape",
        struct.pack(">I", array.ndim)
        + b"".join(struct.pack(">Q", int(size)) for size in array.shape),
    )
    _update_field(digest, f"{tag}.c_order_bytes", contiguous.tobytes(order="C"))


def canonical_frame_semantic_sha256(
    name: str,
    mask: np.ndarray,
    depth_camera_z: np.ndarray,
    K: np.ndarray,
    w2c: np.ndarray,
) -> str:
    """Hash one route input without dtype conversion or coordinate transforms."""
    if _validate_frame_names([name]) != [name]:
        _not_equivalent()
    mask_array = np.asarray(mask)
    depth_array = np.asarray(depth_camera_z)
    K_array = np.asarray(K)
    w2c_array = np.asarray(w2c)
    if (
        mask_array.shape != depth_array.shape
        or mask_array.dtype != np.bool_
        or depth_array.ndim != 2
        or depth_array.dtype.kind != "f"
        or K_array.shape != (3, 3)
        or K_array.dtype.kind != "f"
        or w2c_array.shape not in {(3, 4), (4, 4)}
        or w2c_array.dtype.kind != "f"
    ):
        _not_equivalent()
    digest = hashlib.sha256()
    _update_field(digest, "version", SEMANTIC_HASH_VERSION.encode("ascii"))
    _update_field(digest, "name", name.encode("utf-8"))
    _update_array(digest, "mask", mask_array)
    _update_array(digest, "depth_camera_z", depth_array)
    _update_array(digest, "K", K_array)
    _update_array(digest, "w2c", w2c_array)
    return digest.hexdigest()


def semantic_manifest_sha256(frame_hashes: Iterable[str]) -> str:
    digest = hashlib.sha256()
    _update_field(digest, "version", b"b0-semantic-manifest-v1")
    count = 0
    for value in frame_hashes:
        if not isinstance(value, str) or len(value) != 64:
            _not_equivalent()
        try:
            payload = bytes.fromhex(value)
        except ValueError:
            _not_equivalent()
        _update_field(digest, f"frame[{count}]", payload)
        count += 1
    if count == 0:
        _not_equivalent()
    return digest.hexdigest()


def assert_semantic_hashes_equal(
    left: Sequence[str], right: Sequence[str]
) -> None:
    if list(left) != list(right) or not left:
        _not_equivalent()


def _ray_factor(shape: tuple[int, int], K: np.ndarray) -> np.ndarray:
    intrinsics = np.asarray(K)
    if intrinsics.shape != (3, 3) or intrinsics.dtype.kind != "f":
        _not_equivalent()
    fx = float(intrinsics[0, 0])
    fy = float(intrinsics[1, 1])
    cx = float(intrinsics[0, 2])
    cy = float(intrinsics[1, 2])
    if not all(np.isfinite([fx, fy, cx, cy])) or fx <= 0.0 or fy <= 0.0:
        _not_equivalent()
    height, width = shape
    vv, uu = np.indices((height, width), dtype=np.float64)
    return np.sqrt(((uu - cx) / fx) ** 2 + ((vv - cy) / fy) ** 2 + 1.0)


def camera_z_to_euclidean_ray(depth_camera_z: np.ndarray, K: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth_camera_z)
    if depth.ndim != 2 or depth.dtype.kind != "f":
        _not_equivalent()
    valid = np.isfinite(depth) & (depth > 0)
    output = np.zeros(depth.shape, dtype=np.float64)
    factor = _ray_factor(depth.shape, np.asarray(K))
    output[valid] = depth[valid].astype(np.float64) * factor[valid]
    return output


def euclidean_ray_to_camera_z(depth_ray: np.ndarray, K: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth_ray)
    if depth.ndim != 2 or depth.dtype.kind != "f":
        _not_equivalent()
    valid = np.isfinite(depth) & (depth > 0)
    output = np.zeros(depth.shape, dtype=np.float64)
    factor = _ray_factor(depth.shape, np.asarray(K))
    output[valid] = depth[valid].astype(np.float64) / factor[valid]
    return output


def max_relative_roundtrip_error(
    original: np.ndarray, restored: np.ndarray, mask: np.ndarray
) -> float:
    original_array = np.asarray(original, dtype=np.float64)
    restored_array = np.asarray(restored, dtype=np.float64)
    mask_array = np.asarray(mask)
    if (
        original_array.shape != restored_array.shape
        or original_array.shape != mask_array.shape
        or mask_array.dtype != np.bool_
    ):
        _not_equivalent()
    valid = mask_array & np.isfinite(original_array) & np.isfinite(restored_array)
    if not np.any(valid):
        return 0.0
    denominator = np.maximum(np.abs(original_array[valid]), np.finfo(np.float64).tiny)
    return float(np.max(np.abs(restored_array[valid] - original_array[valid]) / denominator))
