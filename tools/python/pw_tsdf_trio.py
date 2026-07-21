"""Build the controlled B0 TSDF arm from a contract-bound depth cache.

The command is deliberately fail closed.  Before constructing a TSDF volume it
verifies a separately frozen input contract against the exact depth cache,
camera cache, reconstruction list, complete frame universe, and source-image
bytes.  The resulting mesh stays in the input model frame: this route never
applies Sim(3), ICP, smoothing, or route-specific filtering.

Only the frozen ``ofull`` mask and the physical 6 mm TSDF configuration are
supported.  The positional arguments remain for compatibility, but using any
other tag or voxel size is rejected rather than treated as an experiment knob.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2
import numpy as np
import open3d as o3d

import b0_input_contract as input_contract


SCRIPT_PATH = Path(__file__).resolve()
LEGACY_VIEWER_DIR = Path.home() / "Desktop/tiled_414_viewer"
INPUT_CONTRACT_SCHEMA = input_contract.INPUT_CONTRACT_SCHEMA_VERSION
SUPPORTED_TAG = "ofull"
PHYSICAL_VOXEL_MM = 6.0
SDF_TRUNC_VOXELS = 4.0
MASK_SEMANTICS = "isfinite(dm) & (dm > 0)"
FROZEN_METRES_PER_LAPA_UNIT = input_contract.RAW_LAPA_METRES_PER_MODEL_UNIT


class ContractError(RuntimeError):
    """A hard B0 experiment-contract violation."""


def _not_equivalent() -> None:
    raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT)


@dataclass(frozen=True)
class DMCache:
    frames: list[str]
    selected: dict[str, np.ndarray]
    signature: str
    sha256: str
    shape: tuple[int, ...]
    dtype: str


@dataclass(frozen=True)
class ModelCache:
    frames: list[str]
    intrinsics: dict[str, np.ndarray]
    world_to_camera: dict[str, np.ndarray]


@dataclass(frozen=True)
class RouteContract:
    path: Path
    sha256: str
    dataset_id: str
    split_id: str
    coordinate_frame: str
    metres_per_model_unit: float
    transductive_policy: dict[str, object]
    dmcache_sha256: str
    dmcache_signature: str
    dmcache_shape: tuple[int, int, int]
    dmcache_dtype: str
    frame_universe: list[str]
    dm_frame_order_sha256: str
    model_cache_sha256: str
    model_frame_order: list[str]
    model_frame_order_sha256: str
    reconstruction_frames: list[str]
    reconstruction_file_sha256: str
    reconstruction_semantic_sha256: str
    heldout_frames: list[str]
    heldout_file_sha256: str
    heldout_semantic_sha256: str
    image_root_manifest_sha256: str
    images_by_name: dict[str, dict[str, object]]


@dataclass(frozen=True)
class ValidatedInputs:
    output_dir: Path
    contract: RouteContract
    frame_list_path: Path
    dmcache_path: Path
    model_cache_path: Path
    image_root: Path
    dmcache: DMCache
    model: ModelCache
    image_paths: dict[str, Path]


_DM_CACHE: dict[str, np.ndarray] = {}
_IMAGE_PATHS: dict[str, Path] = {}
_IMAGE_SIZE: tuple[int, int] = (0, 0)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controlled B0 6 mm TSDF arm using a frozen input contract."
    )
    parser.add_argument("tag", choices=(SUPPORTED_TAG,))
    parser.add_argument(
        "voxel_mm", nargs="?", default=PHYSICAL_VOXEL_MM, type=float,
        help="fixed physical voxel edge length; only 6 mm is accepted",
    )
    parser.add_argument("--out", required=True, type=_path, metavar="NEW_DIR")
    parser.add_argument("--frame-list", required=True, type=_path, metavar="FILE")
    parser.add_argument("--dmcache", required=True, type=_path, metavar="NPZ")
    parser.add_argument("--model-cache", required=True, type=_path, metavar="NPZ")
    parser.add_argument("--image-root", required=True, type=_path, metavar="DIR")
    parser.add_argument("--input-contract", required=True, type=_path, metavar="JSON")
    parser.add_argument("--split-id", required=True, metavar="ID")
    parser.add_argument(
        "--p1cache", type=_path, default=None,
        help="legacy-compatible argument; recorded as not read",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        not math.isfinite(args.voxel_mm)
        or not math.isclose(args.voxel_mm, PHYSICAL_VOXEL_MM, rel_tol=0.0, abs_tol=1e-12)
    ):
        parser.error("VOXEL_MM is frozen at exactly 6")
    if not args.split_id or args.split_id != args.split_id.strip():
        parser.error("--split-id must be a non-empty unpadded string")
    return args


def validate_frozen_route_parameters(tag: object, voxel_mm: object) -> None:
    try:
        voxel = float(voxel_mm)
    except (TypeError, ValueError):
        raise ContractError("TSDF route parameters differ from frozen ofull/6 mm")
    if (
        tag != SUPPORTED_TAG
        or not math.isfinite(voxel)
        or not math.isclose(voxel, PHYSICAL_VOXEL_MM, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ContractError("TSDF route parameters differ from frozen ofull/6 mm")


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordered_frames_sha256(frames: Sequence[str]) -> str:
    try:
        return input_contract.ordered_frame_names_sha256(frames)
    except input_contract.RouteInputNotEquivalent as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc


def image_identity_manifest_sha256(
    frame_order: Sequence[str], identities: Mapping[str, Mapping[str, object]]
) -> str:
    try:
        return input_contract.image_identity_manifest_sha256(
            frame_order, identities
        )
    except input_contract.RouteInputNotEquivalent as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc


def physical_mm_to_model_units(voxel_mm: float, metres_per_model_unit: float) -> float:
    try:
        millimetres = float(voxel_mm)
        scale = float(metres_per_model_unit)
    except (TypeError, ValueError):
        _not_equivalent()
    if not all(math.isfinite(value) and value > 0 for value in (millimetres, scale)):
        _not_equivalent()
    return (millimetres / 1000.0) / scale


def _require_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        _not_equivalent()
    return resolved


def _require_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        _not_equivalent()
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_output_dir(out: Path, protected_roots: Iterable[Path]) -> Path:
    """Validate without creating anything; existing parent symlinks resolve."""
    resolved = out.expanduser().resolve(strict=False)
    if (
        out.exists()
        or out.is_symlink()
        or resolved.exists()
        or not resolved.parent.is_dir()
    ):
        raise ContractError("--out must be a new directory with an existing parent")
    for protected in protected_roots:
        protected_resolved = protected.expanduser().resolve(strict=False)
        if resolved == protected_resolved or _is_within(resolved, protected_resolved):
            raise ContractError("--out is inside a protected legacy/input tree")
    return resolved


def read_frame_list(path: Path) -> list[str]:
    try:
        return input_contract.parse_frame_list(path)
    except input_contract.RouteInputNotEquivalent as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc


def load_route_contract(path: Path, split_id: str) -> RouteContract:
    source = _require_file(path)
    try:
        payload, contract_sha256 = input_contract.load_input_contract(source)
        selected_split = input_contract.select_input_contract_split(
            payload, split_id
        )
    except input_contract.RouteInputNotEquivalent as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc

    policy = dict(payload["transductive_policy"])
    if policy["route_allowed"] is not True:
        _not_equivalent()
    if selected_split.get("route_allowed", True) is not True:
        _not_equivalent()
    dm = payload["dmcache"]
    model = payload["model_cache"]
    depth = dm["depth"]
    images = payload["images"]
    reconstruction = selected_split["reconstruction"]
    heldout = selected_split["heldout"]

    return RouteContract(
        path=source,
        sha256=contract_sha256,
        dataset_id=str(payload["dataset_id"]),
        split_id=split_id,
        coordinate_frame=str(payload["coordinate_frame"]),
        metres_per_model_unit=float(payload["metres_per_model_unit"]),
        transductive_policy=policy,
        dmcache_sha256=str(dm["sha256"]),
        dmcache_signature=str(dm["signature"]),
        dmcache_shape=tuple(int(value) for value in depth["shape"]),
        dmcache_dtype=str(depth["dtype"]),
        frame_universe=list(dm["frame_order"]),
        dm_frame_order_sha256=str(dm["frame_order_sha256"]),
        model_cache_sha256=str(model["sha256"]),
        model_frame_order=list(model["frame_order"]),
        model_frame_order_sha256=str(model["frame_order_sha256"]),
        reconstruction_frames=list(reconstruction["frames"]),
        reconstruction_file_sha256=str(reconstruction["file_sha256"]),
        reconstruction_semantic_sha256=str(reconstruction["semantic_sha256"]),
        heldout_frames=list(heldout["frames"]),
        heldout_file_sha256=str(heldout["file_sha256"]),
        heldout_semantic_sha256=str(heldout["semantic_sha256"]),
        image_root_manifest_sha256=str(images["root_manifest_sha256"]),
        images_by_name={
            str(name): dict(identity)
            for name, identity in images["by_name"].items()
        },
    )


def load_dmcache(
    path: Path, selected_frames: Sequence[str], contract: RouteContract
) -> DMCache:
    actual_sha = _sha256_file(path)
    if actual_sha != contract.dmcache_sha256:
        _not_equivalent()
    try:
        with np.load(path, allow_pickle=False) as archive:
            if not {"frames", "dm", "sig"}.issubset(archive.files):
                _not_equivalent()
            frames = [str(value) for value in archive["frames"].tolist()]
            signature_raw = np.asarray(archive["sig"])
            depth = np.asarray(archive["dm"])
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc
    if signature_raw.shape != ():
        _not_equivalent()
    signature = str(signature_raw.item())
    if (
        frames != contract.frame_universe
        or _ordered_frames_sha256(frames) != contract.dm_frame_order_sha256
        or signature != contract.dmcache_signature
        or tuple(depth.shape) != contract.dmcache_shape
        or depth.dtype.name != contract.dmcache_dtype
        or len(frames) != len(set(frames))
    ):
        _not_equivalent()
    index = {name: i for i, name in enumerate(frames)}
    if any(name not in index for name in selected_frames):
        _not_equivalent()
    selected = {name: depth[index[name]] for name in selected_frames}
    return DMCache(
        frames=frames,
        selected=selected,
        signature=signature,
        sha256=actual_sha,
        shape=tuple(depth.shape),
        dtype=depth.dtype.name,
    )


def load_model_cache(path: Path, contract: RouteContract | None = None) -> ModelCache:
    if contract is not None and _sha256_file(path) != contract.model_cache_sha256:
        _not_equivalent()
    try:
        with np.load(path, allow_pickle=False) as archive:
            if not {"names", "K", "w2c"}.issubset(archive.files):
                _not_equivalent()
            frames = [str(value) for value in archive["names"].tolist()]
            intrinsics = np.asarray(archive["K"])
            world_to_camera = np.asarray(archive["w2c"])
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc
    count = len(frames)
    if (
        not frames
        or count != len(set(frames))
        or intrinsics.shape != (count, 3, 3)
        or intrinsics.dtype.kind != "f"
        or world_to_camera.shape not in {(count, 3, 4), (count, 4, 4)}
        or world_to_camera.dtype.kind != "f"
        or not np.isfinite(intrinsics).all()
        or not np.isfinite(world_to_camera).all()
        or np.any(intrinsics[:, 0, 0] <= 0)
        or np.any(intrinsics[:, 1, 1] <= 0)
    ):
        _not_equivalent()
    if contract is not None:
        if (
            frames != contract.model_frame_order
            or set(frames) != set(contract.frame_universe)
            or _ordered_frames_sha256(frames) != contract.model_frame_order_sha256
        ):
            _not_equivalent()
    return ModelCache(
        frames=frames,
        intrinsics={name: intrinsics[i] for i, name in enumerate(frames)},
        world_to_camera={name: world_to_camera[i] for i, name in enumerate(frames)},
    )


def _validate_images(
    image_root: Path, contract: RouteContract
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    observed: dict[str, dict[str, object]] = {}
    for name in contract.frame_universe:
        path = (image_root / name).resolve()
        identity = contract.images_by_name[name]
        if not path.is_file() or path.stat().st_size != identity["size_bytes"]:
            _not_equivalent()
        sha = _sha256_file(path)
        if sha != identity["sha256"]:
            _not_equivalent()
        result[name] = path
        observed[name] = {"sha256": sha, "size_bytes": path.stat().st_size}
    if (
        image_identity_manifest_sha256(contract.frame_universe, observed)
        != contract.image_root_manifest_sha256
    ):
        _not_equivalent()
    return result


def validate_frame_join(
    frames: Sequence[str], canonical_frames: Sequence[str],
    dm_frames: set[str], model_frames: set[str],
) -> None:
    if not frames:
        _not_equivalent()
    universe = set(canonical_frames)
    if any(
        name not in universe or name not in dm_frames or name not in model_frames
        for name in frames
    ):
        _not_equivalent()


def validate_route_inputs(args: argparse.Namespace) -> ValidatedInputs:
    contract_path = _require_file(args.input_contract)
    frame_list_path = _require_file(args.frame_list)
    dmcache_path = _require_file(args.dmcache)
    model_path = _require_file(args.model_cache)
    image_root = _require_directory(args.image_root)
    contract = load_route_contract(contract_path, args.split_id)
    selected_frames = read_frame_list(frame_list_path)
    if (
        selected_frames != contract.reconstruction_frames
        or _sha256_file(frame_list_path) != contract.reconstruction_file_sha256
        or _ordered_frames_sha256(selected_frames)
        != contract.reconstruction_semantic_sha256
    ):
        _not_equivalent()
    model = load_model_cache(model_path, contract)
    dmcache = load_dmcache(dmcache_path, selected_frames, contract)
    validate_frame_join(
        selected_frames, contract.frame_universe, set(dmcache.frames), set(model.frames)
    )
    image_paths = _validate_images(image_root, contract)
    output_dir = validate_output_dir(
        args.out,
        {
            LEGACY_VIEWER_DIR,
            contract_path.parent,
            dmcache_path.parent,
            model_path.parent,
            image_root,
        },
    )
    return ValidatedInputs(
        output_dir=output_dir,
        contract=contract,
        frame_list_path=frame_list_path,
        dmcache_path=dmcache_path,
        model_cache_path=model_path,
        image_root=image_root,
        dmcache=dmcache,
        model=model,
        image_paths=image_paths,
    )


def semantic_manifest_provenance(
    frames: Sequence[str],
    depth_by_name: Mapping[str, np.ndarray],
    intrinsics_by_name: Mapping[str, np.ndarray],
    world_to_camera_by_name: Mapping[str, np.ndarray],
) -> dict[str, object]:
    per_frame_hashes: list[str] = []
    try:
        for name in frames:
            depth_camera_z = np.asarray(depth_by_name[name])
            mask = np.isfinite(depth_camera_z) & (depth_camera_z > 0)
            per_frame_hashes.append(
                input_contract.canonical_frame_semantic_sha256(
                    name,
                    mask,
                    depth_camera_z,
                    np.asarray(intrinsics_by_name[name]),
                    np.asarray(world_to_camera_by_name[name]),
                )
            )
        manifest_hash = input_contract.semantic_manifest_sha256(per_frame_hashes)
    except (KeyError, input_contract.RouteInputNotEquivalent) as exc:
        raise ContractError(input_contract.ROUTE_INPUT_NOT_EQUIVALENT) from exc
    return {
        "semantic_hash_schema": input_contract.SEMANTIC_HASH_VERSION,
        "semantic_manifest_hash_schema": "b0-semantic-manifest-v1",
        "semantic_components": {
            "name": "exact_utf8_basename",
            "mask": MASK_SEMANTICS,
            "depth_camera_z": "original_dmcache_float_no_transform",
            "K": "original_model_cache_float_no_transform",
            "w2c": "original_model_cache_float_no_transform",
        },
        "semantic_frame_components": [
            {"name": name, "sha256": semantic_hash}
            for name, semantic_hash in zip(frames, per_frame_hashes, strict=True)
        ],
        "per_frame_semantic_sha256": per_frame_hashes,
        "semantic_manifest_sha256": manifest_hash,
    }


def _load_rgb(name: str) -> np.ndarray:
    path = _IMAGE_PATHS.get(name)
    width, height = _IMAGE_SIZE
    if path is None or width <= 0 or height <= 0:
        _not_equivalent()
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        _not_equivalent()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if rgb.shape[:2] != (height, width):
        rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(rgb, dtype=np.uint8)


def _tsdf_prep_one(name: str) -> tuple[str, np.ndarray, np.ndarray, float]:
    raw_depth = _DM_CACHE.get(name)
    if raw_depth is None:
        _not_equivalent()
    mask = np.isfinite(raw_depth) & (raw_depth > 0)
    depth = np.where(mask, raw_depth, 0.0).astype(np.float32, copy=False)
    kept_fraction = float(np.count_nonzero(mask) / mask.size)
    return name, depth, _load_rgb(name), kept_fraction


def safe_depth_truncation(depth: np.ndarray) -> float:
    valid = np.isfinite(depth) & (depth > 0)
    positive = np.asarray(depth)[valid]
    if positive.size == 0:
        raise ContractError("cannot derive depth_trunc from an empty positive mask")
    maximum = float(np.max(positive))
    truncation = maximum + max(abs(maximum) * 1e-6, 1e-6)
    if not math.isfinite(truncation) or not np.all(positive < truncation):
        raise ContractError("derived depth_trunc would crop a positive depth")
    return truncation


def _as_open3d_extrinsic(value: np.ndarray) -> np.ndarray:
    pose = np.asarray(value, dtype=np.float64)
    if pose.shape == (4, 4):
        return pose
    if pose.shape == (3, 4):
        result = np.eye(4, dtype=np.float64)
        result[:3] = pose
        return result
    _not_equivalent()
    raise AssertionError("unreachable")


def validate_mesh(mesh: object) -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    if vertices.ndim != 2 or vertices.shape[1:] != (3,) or len(vertices) == 0:
        raise ContractError(f"empty or malformed mesh vertices: {vertices.shape}")
    if triangles.ndim != 2 or triangles.shape[1:] != (3,) or len(triangles) == 0:
        raise ContractError(f"empty or malformed mesh triangles: {triangles.shape}")
    if not np.isfinite(vertices).all():
        raise ContractError("mesh contains non-finite vertices")
    if not np.issubdtype(triangles.dtype, np.integer):
        if not np.isfinite(triangles).all() or not np.equal(triangles, np.floor(triangles)).all():
            raise ContractError("mesh triangle indices are non-integral")
    indices = triangles.astype(np.int64, copy=False)
    if indices.min() < 0 or indices.max() >= len(vertices):
        raise ContractError("mesh triangle index is outside the vertex array")
    for attribute in ("vertex_normals", "vertex_colors"):
        if hasattr(mesh, attribute):
            values = np.asarray(getattr(mesh, attribute))
            if values.size and not np.isfinite(values).all():
                raise ContractError(f"mesh contains non-finite {attribute}")
    return vertices, indices


def write_outputs(out: Path, mesh: object, provenance: dict[str, object]) -> None:
    validate_mesh(mesh)
    out.mkdir(mode=0o755, parents=False, exist_ok=False)
    mesh_path = out / "mesh.ply"
    wrote = o3d.io.write_triangle_mesh(
        str(mesh_path), mesh, write_vertex_normals=True,
        write_vertex_colors=True, write_ascii=False,
    )
    if not wrote or not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise ContractError(f"Open3D failed to write a nonempty mesh: {mesh_path}")
    payload = dict(provenance)
    payload["mesh"] = {
        **dict(payload.get("mesh", {})),
        "path": "mesh.ply",
        "bytes": mesh_path.stat().st_size,
        "sha256": _sha256_file(mesh_path),
    }
    (out / "provenance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run(args: argparse.Namespace) -> None:
    validate_frozen_route_parameters(args.tag, args.voxel_mm)
    inputs = validate_route_inputs(args)
    selected_frames = inputs.contract.reconstruction_frames
    semantic_manifest = semantic_manifest_provenance(
        selected_frames,
        inputs.dmcache.selected,
        inputs.model.intrinsics,
        inputs.model.world_to_camera,
    )
    height, width = inputs.contract.dmcache_shape[1:]
    voxel_length = physical_mm_to_model_units(
        PHYSICAL_VOXEL_MM, inputs.contract.metres_per_model_unit
    )
    sdf_trunc = voxel_length * SDF_TRUNC_VOXELS

    _DM_CACHE.clear()
    _DM_CACHE.update(inputs.dmcache.selected)
    _IMAGE_PATHS.clear()
    _IMAGE_PATHS.update(
        {name: inputs.image_paths[name] for name in selected_frames}
    )
    global _IMAGE_SIZE
    _IMAGE_SIZE = (width, height)

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel_length,
        sdf_trunc=sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    started = time.monotonic()
    kept_fractions: list[float] = []
    depth_truncations: dict[str, float] = {}
    integrated = 0
    for ordinal, name in enumerate(selected_frames, 1):
        frame_name, depth, rgb, kept_fraction = _tsdf_prep_one(name)
        kept_fractions.append(kept_fraction)
        if not np.any(depth > 0):
            continue
        depth_truncation = safe_depth_truncation(depth)
        depth_truncations[frame_name] = depth_truncation
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(rgb),
            o3d.geometry.Image(np.ascontiguousarray(depth, dtype=np.float32)),
            depth_scale=1.0,
            depth_trunc=depth_truncation,
            convert_rgb_to_intensity=False,
        )
        intrinsic = inputs.model.intrinsics[frame_name].astype(np.float64)
        camera = o3d.camera.PinholeCameraIntrinsic(
            width, height,
            intrinsic[0, 0], intrinsic[1, 1], intrinsic[0, 2], intrinsic[1, 2],
        )
        volume.integrate(
            rgbd, camera,
            _as_open3d_extrinsic(inputs.model.world_to_camera[frame_name]),
        )
        integrated += 1
        if ordinal == 1 or ordinal % 20 == 0 or ordinal == len(selected_frames):
            print(
                f"[tsdf] {ordinal}/{len(selected_frames)} {frame_name} "
                f"kept={kept_fraction * 100:.1f}% integrated={integrated}",
                flush=True,
            )
    if integrated == 0:
        raise ContractError("no selected frame contained a positive masked depth")

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    vertices, triangles = validate_mesh(mesh)
    elapsed = time.monotonic() - started
    frozen_contract_provenance = {
        "path": str(inputs.contract.path),
        "sha256": inputs.contract.sha256,
        "schema_version": INPUT_CONTRACT_SCHEMA,
        "split_id": inputs.contract.split_id,
        "validated_fields": {
            "dataset_id": inputs.contract.dataset_id,
            "coordinate_frame": inputs.contract.coordinate_frame,
            "metres_per_model_unit": inputs.contract.metres_per_model_unit,
            "transductive_policy": inputs.contract.transductive_policy,
            "dmcache_frame_order_sha256": inputs.contract.dm_frame_order_sha256,
            "model_cache_frame_order_sha256": (
                inputs.contract.model_frame_order_sha256
            ),
            "reconstruction_file_sha256": (
                inputs.contract.reconstruction_file_sha256
            ),
            "reconstruction_semantic_sha256": (
                inputs.contract.reconstruction_semantic_sha256
            ),
            "heldout_file_sha256": inputs.contract.heldout_file_sha256,
            "heldout_semantic_sha256": inputs.contract.heldout_semantic_sha256,
            "image_root_manifest_sha256": (
                inputs.contract.image_root_manifest_sha256
            ),
        },
        "hash_algorithms": {
            "frame_order_and_split_semantic": (
                'SHA-256 of "".join(f"{name}\\n") UTF-8 in frozen order'
            ),
            "frame_list_file_sha256": "SHA-256 of exact raw frame-list file bytes",
            "images_root_manifest": (
                "SHA-256 of name<TAB>sha256<TAB>size_bytes<LF> UTF-8 "
                "in dmcache.frame_order"
            ),
        },
    }
    provenance: dict[str, object] = {
        "schema": "pocketworld.b0.tsdf.provenance.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": {"path": str(SCRIPT_PATH), "sha256": _sha256_file(SCRIPT_PATH)},
        "tag": SUPPORTED_TAG,
        "voxel_mm": PHYSICAL_VOXEL_MM,
        "dataset_id": inputs.contract.dataset_id,
        "split_id": inputs.contract.split_id,
        "coordinate_frame": inputs.contract.coordinate_frame,
        "metres_per_model_unit": inputs.contract.metres_per_model_unit,
        "transductive_policy": inputs.contract.transductive_policy,
        "frame_count": len(selected_frames),
        "frame_order": selected_frames,
        "frame_list_sha256": inputs.contract.reconstruction_file_sha256,
        "dmcache_sha256": inputs.dmcache.sha256,
        "dmcache_signature": inputs.dmcache.signature,
        "model_cache_sha256": inputs.contract.model_cache_sha256,
        **semantic_manifest,
        "input_contract": frozen_contract_provenance,
        "frozen_input_identity_contract": frozen_contract_provenance,
        "inputs": {
            "dmcache": {
                "path": str(inputs.dmcache_path),
                "bytes": inputs.dmcache_path.stat().st_size,
                "sha256": inputs.dmcache.sha256,
                "signature": inputs.dmcache.signature,
                "shape": list(inputs.dmcache.shape),
                "dtype": inputs.dmcache.dtype,
                "frame_order_sha256": inputs.contract.dm_frame_order_sha256,
            },
            "model_cache": {
                "path": str(inputs.model_cache_path),
                "bytes": inputs.model_cache_path.stat().st_size,
                "sha256": inputs.contract.model_cache_sha256,
                "frame_order_sha256": inputs.contract.model_frame_order_sha256,
            },
            "frame_list": {
                "path": str(inputs.frame_list_path),
                "bytes": inputs.frame_list_path.stat().st_size,
                "file_sha256": inputs.contract.reconstruction_file_sha256,
                "semantic_sha256": inputs.contract.reconstruction_semantic_sha256,
            },
            "images": {
                "root": str(inputs.image_root),
                "root_manifest_sha256": inputs.contract.image_root_manifest_sha256,
                "identity_count": len(inputs.contract.images_by_name),
                "role": "RGB color only; image pixels do not alter TSDF geometry",
            },
        },
        "input_equivalence_contract": {
            **semantic_manifest,
            "depth_semantics": "camera_z",
            "mask_semantics": MASK_SEMANTICS,
            "p1cache_dependency": False,
            "legacy_p1cache_argument_not_read": (
                str(args.p1cache.expanduser().resolve(strict=False))
                if args.p1cache is not None else None
            ),
            "neighbor_policy": (
                "not_recomputed; contract-bound masked depth is common to both arms"
            ),
            "status": "VALIDATED_FOR_TSDF_ARM",
        },
        "coordinate_transform": {
            "mesh_output": inputs.contract.coordinate_frame,
            "metres_per_model_unit": inputs.contract.metres_per_model_unit,
            "transform_applied_by_route": False,
            "sim3_applied_to_mesh": False,
            "icp_applied_to_mesh": False,
        },
        "tsdf": {
            "physical_voxel_mm": PHYSICAL_VOXEL_MM,
            "model_frame_voxel_length": voxel_length,
            "model_frame_sdf_trunc": sdf_trunc,
            "sdf_trunc_voxels": SDF_TRUNC_VOXELS,
            "route_parameter_tuning": False,
            "depth_trunc_policy": (
                "per-frame max finite positive depth plus deterministic epsilon"
            ),
            "depth_trunc_by_frame": depth_truncations,
            "integration_order": selected_frames,
            "selected_frames": len(selected_frames),
            "integrated_frames": integrated,
            "mean_positive_mask_fraction": float(np.mean(kept_fractions)),
            "wall_seconds": elapsed,
        },
        "mesh": {
            "vertices": int(len(vertices)),
            "triangles": int(len(triangles)),
            "bbox_min": vertices.min(axis=0).tolist(),
            "bbox_max": vertices.max(axis=0).tolist(),
            "finite": True,
        },
    }
    write_outputs(inputs.output_dir, mesh, provenance)
    print(
        f"[tsdf] wrote isolated {inputs.contract.coordinate_frame} result "
        f"{inputs.output_dir} ({len(vertices):,} vertices, "
        f"{len(triangles):,} triangles, {elapsed:.1f}s)",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        _run(parse_args(argv))
    except ContractError as exc:
        print(f"B0_CONTRACT_ERROR: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
