"""Controlled FuseCut-vs-TSDF mesh evaluation primitives.

This module deliberately has no Open3D import.  It evaluates both meshers in
the coordinate frame frozen by a shared ``b0-input-contract-v1`` against the
same camera-Z observations.  The caller is responsible for ray casting;
:mod:`pw_mesh_bench` provides that thin adapter and imports Open3D only when an
actual mesh is evaluated.

The measurements are observation-consistency diagnostics, not ground truth.
No alignment, scale fitting, Sim(3), ICP, or per-route tuning is performed.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import struct
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


ROUTE_INPUT_NOT_EQUIVALENT = "ROUTE_INPUT_NOT_EQUIVALENT"
COORDINATE_FRAME_MISMATCH = "COORDINATE_FRAME_MISMATCH"
METRIC_UNDEFINED = "METRIC_UNDEFINED"

FROZEN_METRES_PER_LAPA_UNIT = 0.21677133346045502
FROZEN_SIM3_SHA256 = (
    "ca5e4b72dcb4e6a7bee8af8182c2947e006de5a59e8ca7c1e030ffee288b70f4"
)
SUPPORTED_COORDINATE_FRAMES = {
    "raw_lapa_model",
    "metric_arkit_cv",
    "optimized_sfm_cv",
}
PHYSICAL_THRESHOLDS_METRES = {
    "depth_tolerance_floor": 0.020,
    "unsupported_surface": 0.020,
    "shell_cluster": 0.0001,
    "shell_min_separation": 0.003,
    "shell_max_separation": 0.050,
    "planar_residual": 0.005,
}

FINAL_BOOTSTRAP_REPLICATES = 10_000
FINAL_BOOTSTRAP_SEED = 20260721

# B0.6 is the authority for *every* quality cohort.  In particular, the
# smaller cohort is a sequencing gate, not permission to relax the scientific
# acceptance criteria.  The values below are validated against (and then
# reported from) the supplied preregistration contract.
STRICT_GATE_CONTRACT = {
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

STRICT_IMPROVEMENT_CONTRACT = {
    "bootstrap_draws": FINAL_BOOTSTRAP_REPLICATES,
    "seed": FINAL_BOOTSTRAP_SEED,
    "confidence_interval": "two-sided percentile 95%; use lower bound",
    "required_low_texture_coverage_lower_bound": 0.05,
    "required_weak_support_coverage_lower_bound": 0.05,
    "also_requires_all_noninferiority_gates": True,
    "unit": "paired held-out frame",
}

CONTRACT_ARRAY_KEYS = (
    "frames",
    "depth",
    "K",
    "w2c",
    "roi",
    "low_texture",
    "weak_support",
    "planar_single_surface",
)


class EvaluationContractError(ValueError):
    """Hard contract violation carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _validated_scale(metres_per_model_unit: float) -> float:
    scale = float(metres_per_model_unit)
    if not np.isfinite(scale) or scale <= 0:
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH, "metres-per-model-unit scale must be finite and positive"
        )
    return scale


def physical_metres_to_model_units(
    metres: Any, *, metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT
) -> np.ndarray | float:
    """Convert a physical threshold without transforming evaluated geometry."""

    scale = _validated_scale(metres_per_model_unit)
    converted = np.asarray(metres, dtype=np.float64) / scale
    return float(converted) if converted.ndim == 0 else converted


def model_units_to_physical_mm(
    model_units: Any, *, metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT
) -> np.ndarray | float:
    scale = _validated_scale(metres_per_model_unit)
    converted = np.asarray(model_units, dtype=np.float64) * scale * 1000.0
    return float(converted) if converted.ndim == 0 else converted


def _validated_contract_identity(
    *,
    coordinate_frame: str,
    metres_per_model_unit: float,
    input_contract_sha256: str,
    split_id: str,
) -> tuple[str, float, str, str]:
    if coordinate_frame not in SUPPORTED_COORDINATE_FRAMES:
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH,
            f"unsupported contract coordinate frame {coordinate_frame!r}",
        )
    scale = _validated_scale(metres_per_model_unit)
    if coordinate_frame == "raw_lapa_model" and (
        scale.hex() != FROZEN_METRES_PER_LAPA_UNIT.hex()
    ):
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH, "raw_lapa_model scale differs from the freeze"
        )
    if coordinate_frame == "metric_arkit_cv" and scale.hex() != float(1.0).hex():
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH, "metric_arkit_cv must use one metre per model unit"
        )
    if (
        not isinstance(input_contract_sha256, str)
        or len(input_contract_sha256) != 64
    ):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, "input contract identity is not SHA-256"
        )
    try:
        bytes.fromhex(input_contract_sha256)
    except ValueError as error:
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, "input contract identity is not hexadecimal"
        ) from error
    if not isinstance(split_id, str) or not split_id or split_id != split_id.strip():
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, "input contract split identity is invalid"
        )
    return coordinate_frame, scale, input_contract_sha256, split_id


def metric_unit_contract(
    *,
    coordinate_frame: str,
    metres_per_model_unit: float,
    input_contract_sha256: str,
    split_id: str,
) -> dict[str, Any]:
    """Return the metric conversion frozen by one shared input contract.

    The scale converts physical thresholds only.  It is never applied to mesh,
    camera, or depth geometry.  The legacy raw-LAPA Sim(3) identity is retained
    as semantics bound by the input-contract hash, not as an evaluator action.
    """

    frame, scale, contract_sha256, selected_split = _validated_contract_identity(
        coordinate_frame=coordinate_frame,
        metres_per_model_unit=metres_per_model_unit,
        input_contract_sha256=input_contract_sha256,
        split_id=split_id,
    )
    result: dict[str, Any] = {
        "coordinate_frame": frame,
        "metres_per_model_unit": scale,
        "input_contract_sha256": contract_sha256,
        "split_id": selected_split,
        "applied_to_geometry": False,
        "used_only_for_metric_unit_conversion": True,
        "thresholds_physical_metres": dict(PHYSICAL_THRESHOLDS_METRES),
        "thresholds_contract_model_units": {
            name: physical_metres_to_model_units(value, metres_per_model_unit=scale)
            for name, value in PHYSICAL_THRESHOLDS_METRES.items()
        },
    }
    if frame == "raw_lapa_model":
        result["legacy_raw_lapa_frozen_sim3_sha256"] = FROZEN_SIM3_SHA256
        result["legacy_raw_lapa_sim3_applied_by_evaluator"] = False
    return result


def require_matching_metric_unit_contracts(
    tsdf_contract: Any,
    fusecut_contract: Any,
    *,
    coordinate_frame: str,
    metres_per_model_unit: float,
    input_contract_sha256: str,
    split_id: str,
) -> None:
    expected = metric_unit_contract(
        coordinate_frame=coordinate_frame,
        metres_per_model_unit=metres_per_model_unit,
        input_contract_sha256=input_contract_sha256,
        split_id=split_id,
    )
    for label, candidate in (("TSDF", tsdf_contract), ("FuseCut", fusecut_contract)):
        if not isinstance(candidate, Mapping):
            raise EvaluationContractError(
                COORDINATE_FRAME_MISMATCH, f"{label} lacks a metric unit contract"
            )
        if dict(candidate) != expected:
            raise EvaluationContractError(
                COORDINATE_FRAME_MISMATCH,
                f"{label} metric unit contract differs from the shared input contract",
            )


def _hash_array(hasher: Any, name: str, value: Any) -> None:
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, f"contract member {name!r} has object dtype"
        )
    contiguous = np.ascontiguousarray(array)
    header = json.dumps(
        {
            "name": name,
            "dtype": contiguous.dtype.str,
            "shape": list(contiguous.shape),
            "nbytes": contiguous.nbytes,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    hasher.update(struct.pack(">Q", len(header)))
    hasher.update(header)
    raw = memoryview(contiguous).cast("B")
    hasher.update(struct.pack(">Q", len(raw)))
    hasher.update(raw)


def frozen_input_digest(contract_arrays: Mapping[str, Any]) -> str:
    """Hash every frozen input member, including dtype, shape, order and bits."""

    missing = [key for key in CONTRACT_ARRAY_KEYS if key not in contract_arrays]
    extra = sorted(set(contract_arrays) - set(CONTRACT_ARRAY_KEYS))
    if missing or extra:
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            f"contract schema mismatch; missing={missing}, extra={extra}",
        )
    hasher = hashlib.sha256()
    hasher.update(b"pocketworld.mesh-ab.input-contract.v1\0")
    for key in CONTRACT_ARRAY_KEYS:
        _hash_array(hasher, key, contract_arrays[key])
    return hasher.hexdigest()


def require_equivalent_route_inputs(
    expected_digest: str, tsdf_digest: str, fusecut_digest: str
) -> None:
    """Fail before metric comparison unless both actual routes equal the freeze."""

    if not expected_digest or not (
        tsdf_digest == expected_digest == fusecut_digest
    ):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            "expected, TSDF, and FuseCut contract digests are not identical",
        )


def vertices_to_contract_model(vertices: Any, storage_frame: str) -> np.ndarray:
    """Decode mesh storage into the already-frozen contract model frame.

    ``contract_model`` is bit-for-bit unchanged.  AliceVision OBJ output uses
    its fixed camera/object storage rotation, so ``alicevision_obj`` is decoded
    with ``diag(1,-1,-1)``.  This is a storage convention conversion only: it
    contains no LAPA transform, fitted alignment, scale, Sim(3), or ICP.
    """

    result = np.asarray(vertices, dtype=np.float64)
    if result.ndim != 2 or result.shape[1:] != (3,):
        raise EvaluationContractError(COORDINATE_FRAME_MISMATCH, "vertices must be N x 3")
    if storage_frame == "contract_model":
        return result.copy()
    if storage_frame == "alicevision_obj":
        return result @ np.diag([1.0, -1.0, -1.0])
    raise EvaluationContractError(
        COORDINATE_FRAME_MISMATCH, f"unsupported mesh storage frame {storage_frame!r}"
    )


def _base_topology_result(*reasons: str) -> dict[str, Any]:
    return {
        "finite": "nonfinite" not in reasons,
        "degenerate": bool(reasons),
        "degenerate_reasons": list(dict.fromkeys(reasons)),
        "vertex_count": 0,
        "face_count": 0,
        "valid_face_count": 0,
        "zero_area_face_count": 0,
        "zero_area_face_fraction": None,
        "unique_edge_count": 0,
        "nonmanifold_edge_count": 0,
        "nonmanifold_edge_ratio": None,
    }


def mesh_topology_metrics(vertices: Any, faces: Any) -> dict[str, Any]:
    """Validate a triangle mesh and count incidence>2 undirected edges.

    Boundary edges (incidence one) are intentionally not non-manifold.  A
    single triangle is flagged as a degenerate evaluation specimen even though
    its three indices are syntactically valid.
    """

    try:
        v = np.asarray(vertices)
        f = np.asarray(faces)
    except Exception:
        return _base_topology_result("bad_shape")
    reasons: list[str] = []
    if v.ndim != 2 or v.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,):
        result = _base_topology_result("bad_shape")
        if v.ndim == 2:
            result["vertex_count"] = int(v.shape[0])
        if f.ndim == 2:
            result["face_count"] = int(f.shape[0])
        return result
    nv, nf = int(v.shape[0]), int(f.shape[0])
    if nv == 0 or nf == 0:
        reasons.append("empty")
    if nf == 1:
        reasons.append("single_triangle")
    finite = bool(np.issubdtype(v.dtype, np.number) and np.isfinite(v).all())
    if not finite:
        reasons.append("nonfinite")
    integer_faces = bool(np.issubdtype(f.dtype, np.integer))
    if not integer_faces:
        reasons.append("bad_index")
    else:
        valid_indices = bool(nv > 0 and np.all((f >= 0) & (f < nv)))
        if not valid_indices:
            reasons.append("bad_index")
        repeated = bool(nf and np.any(np.sort(f, axis=1)[:, 1:] == np.sort(f, axis=1)[:, :-1]))
        if repeated:
            reasons.append("zero_area")

    edge_count = nonmanifold = 0
    valid_face_count = 0
    zero_area_face_count = 0
    zero_area_face_fraction: float | None = None
    ratio: float | None = None
    can_measure = finite and integer_faces and "bad_index" not in reasons and nv and nf
    if can_measure:
        tri = f.astype(np.int64, copy=False)
        area2 = np.linalg.norm(
            np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1
        )
        zero_area = (~np.isfinite(area2)) | (area2 <= np.finfo(np.float64).eps)
        zero_area_face_count = int(np.count_nonzero(zero_area))
        valid_face_count = int(nf - zero_area_face_count)
        zero_area_face_fraction = float(zero_area_face_count / nf)
        if zero_area_face_count:
            reasons.append("zero_area")
        edges = np.concatenate((tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]))
        edges.sort(axis=1)
        incidences = Counter(map(tuple, edges.tolist()))
        edge_count = len(incidences)
        nonmanifold = sum(count > 2 for count in incidences.values())
        ratio = float(nonmanifold / edge_count) if edge_count else None

    return {
        "finite": finite,
        "degenerate": bool(reasons),
        "degenerate_reasons": list(dict.fromkeys(reasons)),
        "vertex_count": nv,
        "face_count": nf,
        "valid_face_count": valid_face_count,
        "zero_area_face_count": zero_area_face_count,
        "zero_area_face_fraction": zero_area_face_fraction,
        "unique_edge_count": edge_count,
        "nonmanifold_edge_count": nonmanifold,
        "nonmanifold_edge_ratio": ratio,
    }


def evaluation_triangle_mask(vertices: Any, faces: Any) -> np.ndarray:
    """Select finite, positive-area triangles for metric ray casting.

    Topology is reported on the raw backend output.  This shared face-level
    sanitation is applied identically to both routes so isolated zero-area
    triangles cannot make every held-out metric undefined.
    """

    v = np.asarray(vertices)
    f = np.asarray(faces)
    if (
        v.ndim != 2
        or v.shape[1:] != (3,)
        or f.ndim != 2
        or f.shape[1:] != (3,)
        or not np.issubdtype(v.dtype, np.number)
        or not np.isfinite(v).all()
        or not np.issubdtype(f.dtype, np.integer)
        or len(v) == 0
        or np.any((f < 0) | (f >= len(v)))
    ):
        raise EvaluationContractError(METRIC_UNDEFINED, "mesh cannot be sanitized safely")
    tri = f.astype(np.int64, copy=False)
    area2 = np.linalg.norm(
        np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]), axis=1
    )
    return np.isfinite(area2) & (area2 > np.finfo(np.float64).eps)


def sanitize_evaluation_faces(
    vertices: Any, faces: Any
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply the frozen face filter and return its auditable counts."""

    f = np.asarray(faces)
    mask = evaluation_triangle_mask(vertices, f)
    selected = f[mask]
    if len(selected) < 2:
        raise EvaluationContractError(
            METRIC_UNDEFINED,
            "fewer than two positive-area triangles remain after shared sanitation",
        )
    audit = {
        "policy": "drop_area2_le_float64_epsilon",
        "applied_identically_to_both_routes": True,
        "input_face_count": int(len(f)),
        "excluded_face_count": int(len(f) - len(selected)),
        "evaluated_face_count": int(len(selected)),
    }
    return selected, audit


def depth_tolerance(
    observed_z: Any, *, metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT
) -> np.ndarray:
    z = np.asarray(observed_z, dtype=np.float64)
    floor = physical_metres_to_model_units(
        PHYSICAL_THRESHOLDS_METRES["depth_tolerance_floor"],
        metres_per_model_unit=metres_per_model_unit,
    )
    return np.maximum(floor, 0.02 * z)


def ray_parameter_to_camera_z(t_hit: Any, directions_camera: Any) -> np.ndarray:
    """Convert a ray's first positive intersection parameter to camera-Z.

    Open3D defines a ray point as ``origin + t_hit * direction``.  Therefore
    camera-Z is ``t_hit * direction_camera.z`` whether directions are unit
    length or use the benchmark's convenient ``[x, y, 1]`` convention.
    """

    parameter = np.asarray(t_hit, dtype=np.float64)
    directions = np.asarray(directions_camera, dtype=np.float64)
    if directions.shape != parameter.shape + (3,):
        raise ValueError("directions_camera must have t_hit.shape + (3,)")
    return parameter * directions[..., 2]


def observed_normals_camera_z(
    depth: Any,
    K: Any,
    *,
    metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT,
) -> tuple[np.ndarray, np.ndarray]:
    """Four-neighbour central-difference normals, oriented toward the camera."""

    z = np.asarray(depth, dtype=np.float64)
    intrinsics = np.asarray(K, dtype=np.float64)
    if z.ndim != 2 or intrinsics.shape != (3, 3):
        raise ValueError("depth must be H x W and K must be 3 x 3")
    height, width = z.shape
    yy, xx = np.indices((height, width), dtype=np.float64)
    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]
    if not np.isfinite([fx, fy, cx, cy]).all() or fx == 0 or fy == 0:
        raise ValueError("invalid intrinsics")
    points = np.stack(((xx - cx) * z / fx, (yy - cy) * z / fy, z), axis=-1)
    normals = np.zeros_like(points)
    valid = np.zeros(z.shape, dtype=bool)
    if height < 3 or width < 3:
        return normals, valid

    center = z[1:-1, 1:-1]
    neighbours = (z[1:-1, :-2], z[1:-1, 2:], z[:-2, 1:-1], z[2:, 1:-1])
    tau = depth_tolerance(center, metres_per_model_unit=metres_per_model_unit)
    interior_valid = np.isfinite(center) & (center > 0)
    for neighbour in neighbours:
        interior_valid &= np.isfinite(neighbour) & (neighbour > 0)
        interior_valid &= np.abs(neighbour - center) <= tau
    dx = points[1:-1, 2:] - points[1:-1, :-2]
    dy = points[2:, 1:-1] - points[:-2, 1:-1]
    n = np.cross(dx, dy)
    lengths = np.linalg.norm(n, axis=-1)
    interior_valid &= np.isfinite(lengths) & (lengths > 0)
    safe = np.where(lengths > 0, lengths, 1.0)
    n = n / safe[..., None]
    toward = -points[1:-1, 1:-1]
    flip = np.sum(n * toward, axis=-1) < 0
    n[flip] *= -1
    normals[1:-1, 1:-1] = n
    valid[1:-1, 1:-1] = interior_valid
    normals[~valid] = 0
    return normals, valid


def _normal_angles(
    observed_z: np.ndarray,
    hit_z: np.ndarray,
    hit_normals: np.ndarray,
    K: np.ndarray,
    consistent: np.ndarray,
    metres_per_model_unit: float,
) -> tuple[np.ndarray, np.ndarray]:
    obs_normals, obs_valid = observed_normals_camera_z(
        observed_z, K, metres_per_model_unit=metres_per_model_unit
    )
    hn = np.asarray(hit_normals, dtype=np.float64).copy()
    if hn.shape != observed_z.shape + (3,):
        raise ValueError("hit_normals must be H x W x 3")
    lengths = np.linalg.norm(hn, axis=-1)
    hit_valid = np.isfinite(hn).all(axis=-1) & np.isfinite(lengths) & (lengths > 0)
    hn /= np.where(lengths > 0, lengths, 1.0)[..., None]

    yy, xx = np.indices(observed_z.shape, dtype=np.float64)
    rays = np.stack(
        ((xx - K[0, 2]) / K[0, 0], (yy - K[1, 2]) / K[1, 1], np.ones_like(xx)), axis=-1
    )
    hit_points = rays * hit_z[..., None]
    flip = np.sum(hn * (-hit_points), axis=-1) < 0
    hn[flip] *= -1
    valid = consistent & obs_valid & hit_valid
    dots = np.clip(np.sum(obs_normals * hn, axis=-1), -1.0, 1.0)
    angles = np.degrees(np.arccos(dots))
    return angles, valid


def evaluate_frame_observations(
    observed_z: Any,
    hit_z: Any,
    *,
    masks: Mapping[str, Any],
    K: Any | None = None,
    hit_normals: Any | None = None,
    metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT,
) -> dict[str, Any]:
    """Compute per-frame count sums and pooled per-pixel residual samples."""

    z = np.asarray(observed_z, dtype=np.float64)
    hit = np.asarray(hit_z, dtype=np.float64)
    if z.ndim != 2 or hit.shape != z.shape:
        raise ValueError("observed_z and hit_z must have the same H x W shape")
    for required in ("roi", "low_texture", "weak_support"):
        if required not in masks or np.asarray(masks[required]).shape != z.shape:
            raise ValueError(f"missing or invalid {required} mask")
    valid_obs = np.asarray(masks["roi"], dtype=bool) & np.isfinite(z) & (z > 0)
    valid_hit = np.isfinite(hit) & (hit > 0)
    scale = _validated_scale(metres_per_model_unit)
    tolerance = depth_tolerance(z, metres_per_model_unit=scale)
    consistent = valid_obs & valid_hit & (np.abs(z - hit) <= tolerance)
    unsupported_threshold = physical_metres_to_model_units(
        PHYSICAL_THRESHOLDS_METRES["unsupported_surface"],
        metres_per_model_unit=scale,
    )
    unsupported = valid_obs & valid_hit & ((z - hit) > unsupported_threshold)
    absrel = np.abs(z - hit) / np.maximum(z, np.finfo(np.float64).tiny)

    angles: np.ndarray | None = None
    normal_valid: np.ndarray | None = None
    if K is not None and hit_normals is not None:
        angles, normal_valid = _normal_angles(
            z,
            hit,
            np.asarray(hit_normals),
            np.asarray(K, dtype=np.float64),
            consistent,
            scale,
        )

    subset_masks = {
        "all": np.ones(z.shape, dtype=bool),
        "low_texture": np.asarray(masks["low_texture"], dtype=bool),
        "weak_support": np.asarray(masks["weak_support"], dtype=bool),
    }
    subset_masks["union"] = subset_masks["low_texture"] | subset_masks["weak_support"]
    output: dict[str, Any] = {}
    for name, subset in subset_masks.items():
        eligible = valid_obs & subset
        hits = eligible & valid_hit
        normal_selection = eligible & normal_valid if normal_valid is not None else np.zeros_like(eligible)
        output[name] = {
            "coverage_numerator": int(np.count_nonzero(consistent & subset)),
            "coverage_denominator": int(np.count_nonzero(eligible)),
            "unsupported_numerator": int(np.count_nonzero(unsupported & subset)),
            "unsupported_hit_denominator": int(np.count_nonzero(hits)),
            "unsupported_v_denominator": int(np.count_nonzero(eligible)),
            # Keep dense samples as NumPy chunks.  Converting full-scene
            # samples to Python floats multiplies memory use and defeats the
            # per-frame streaming ray-cast path.
            "absrel_values": np.ascontiguousarray(absrel[hits], dtype=np.float64),
            "normal_angle_values": (
                np.ascontiguousarray(angles[normal_selection], dtype=np.float64)
                if angles is not None
                else np.empty(0, dtype=np.float64)
            ),
            "normal_candidate_count": int(np.count_nonzero(normal_selection)),
        }
    return output


def _unit_normal(value: np.ndarray) -> np.ndarray | None:
    n = np.asarray(value, dtype=np.float64)
    if n.shape != (3,) or not np.isfinite(n).all():
        return None
    length = float(np.linalg.norm(n))
    return n / length if length > 0 else None


def _cluster_intersections(
    depths: np.ndarray, normals: np.ndarray, tolerance_model_units: float
) -> list[tuple[float, np.ndarray | None]]:
    pairs = []
    for depth, normal in zip(np.asarray(depths).reshape(-1), np.asarray(normals).reshape(-1, 3)):
        if np.isfinite(depth) and depth > 0:
            pairs.append((float(depth), _unit_normal(normal)))
    pairs.sort(key=lambda pair: pair[0])
    clusters: list[list[tuple[float, np.ndarray | None]]] = []
    for pair in pairs:
        if not clusters or pair[0] - clusters[-1][-1][0] > tolerance_model_units:
            clusters.append([pair])
        else:
            clusters[-1].append(pair)
    result = []
    for cluster in clusters:
        center = float(np.mean([pair[0] for pair in cluster]))
        available = [pair[1] for pair in cluster if pair[1] is not None]
        normal = _unit_normal(np.sum(available, axis=0)) if available else None
        result.append((center, normal))
    return result


def double_shell_metrics(
    *,
    observed_z: Any,
    eligible_mask: Any,
    intersections_z: Sequence[Any] | None = None,
    intersection_normals: Sequence[Any] | None = None,
    sparse_intersections: Mapping[int, tuple[Any, Any]] | None = None,
    metres_per_model_unit: float = FROZEN_METRES_PER_LAPA_UNIT,
) -> dict[str, Any]:
    """Measure nearby, *same-facing* secondary surface clusters.

    The denominator contains only frozen planar/single-surface rays for which a
    primary cluster exists within the per-observation depth tolerance.  Signed
    mesh normals are intentionally preserved.  Two successive intersections
    of a normally wound closed surface have opposed normals (entry/exit) and
    are not a duplicate shell; two nearby copies of the same surface have
    agreeing normals and are.  Callers must therefore never orient every
    multi-hit normal toward the camera before invoking this function.
    """

    z = np.asarray(observed_z, dtype=np.float64).reshape(-1)
    eligible = np.asarray(eligible_mask, dtype=bool).reshape(-1)
    if len(z) != len(eligible):
        raise ValueError("double-shell observation and eligibility arrays must have equal lengths")
    dense_mode = sparse_intersections is None
    if dense_mode:
        if intersections_z is None or intersection_normals is None or not (
            len(z) == len(intersections_z) == len(intersection_normals)
        ):
            raise ValueError("double-shell dense ray arrays must have equal lengths")
    elif intersections_z is not None or intersection_normals is not None:
        raise ValueError("provide either dense or sparse intersections, not both")
    eligible_primary = 0
    separations: list[float] = []
    cos20 = math.cos(math.radians(20.0))
    scale = _validated_scale(metres_per_model_unit)
    cluster_tolerance = physical_metres_to_model_units(
        PHYSICAL_THRESHOLDS_METRES["shell_cluster"], metres_per_model_unit=scale
    )
    min_separation = physical_metres_to_model_units(
        PHYSICAL_THRESHOLDS_METRES["shell_min_separation"], metres_per_model_unit=scale
    )
    max_separation = physical_metres_to_model_units(
        PHYSICAL_THRESHOLDS_METRES["shell_max_separation"], metres_per_model_unit=scale
    )
    for index in np.flatnonzero(eligible & np.isfinite(z) & (z > 0)):
        if sparse_intersections is not None:
            pair = sparse_intersections.get(int(index))
            if pair is None:
                continue
            ray_depths, ray_normals = pair
        else:
            assert intersections_z is not None and intersection_normals is not None
            ray_depths = intersections_z[index]
            ray_normals = intersection_normals[index]
        clusters = _cluster_intersections(
            np.asarray(ray_depths),
            np.asarray(ray_normals),
            cluster_tolerance,
        )
        if not clusters:
            continue
        primary_index = min(range(len(clusters)), key=lambda j: abs(clusters[j][0] - z[index]))
        primary_z, primary_normal = clusters[primary_index]
        if abs(primary_z - z[index]) > depth_tolerance(
            np.asarray(z[index]), metres_per_model_unit=scale
        ):
            continue
        eligible_primary += 1
        candidates = []
        for j, (secondary_z, secondary_normal) in enumerate(clusters):
            if j == primary_index:
                continue
            separation = abs(secondary_z - primary_z)
            if not (min_separation <= separation <= max_separation):
                continue
            if primary_normal is None or secondary_normal is None:
                continue
            if float(np.dot(primary_normal, secondary_normal)) >= cos20:
                candidates.append(separation)
        if candidates:
            separations.append(min(candidates))
    event_count = len(separations)
    return {
        "eligible_rays": eligible_primary,
        "event_count": event_count,
        "rate": float(event_count / eligible_primary) if eligible_primary else None,
        "separations_mm": [
            float(model_units_to_physical_mm(value, metres_per_model_unit=scale))
            for value in separations
        ],
        "separation_p95_mm": (
            float(
                np.quantile(
                    model_units_to_physical_mm(
                        np.asarray(separations), metres_per_model_unit=scale
                    ),
                    0.95,
                )
            )
            if separations
            else None
        ),
    }


def _fraction(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _percentile(values: Sequence[float], quantile: float, scale: float = 1.0) -> float | None:
    return float(np.quantile(np.asarray(values, dtype=np.float64), quantile) * scale) if values else None


def _chunked_percentile(
    chunks: Sequence[np.ndarray], quantile: float, scale: float = 1.0
) -> float | None:
    nonempty = [
        np.asarray(chunk, dtype=np.float64).reshape(-1)
        for chunk in chunks
        if np.asarray(chunk).size
    ]
    if not nonempty:
        return None
    pooled = nonempty[0] if len(nonempty) == 1 else np.concatenate(nonempty)
    return float(np.quantile(pooled, quantile) * scale)


def aggregate_frame_results(frames: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Pool pixel samples and preserve per-frame count sums for bootstrap."""

    subset_names = ("all", "low_texture", "weak_support", "union")
    accumulators = {
        name: {
            "coverage_numerator": 0,
            "coverage_denominator": 0,
            "unsupported_numerator": 0,
            "unsupported_hit_denominator": 0,
            "unsupported_v_denominator": 0,
            "absrel_chunks": [],
            "normal_angle_chunks": [],
        }
        for name in subset_names
    }
    frame_counts = {name: [] for name in subset_names}
    shell_eligible = shell_events = 0
    shell_separations: list[float] = []
    for frame in frames:
        for name in subset_names:
            current = frame[name]
            accumulator = accumulators[name]
            for key in (
                "coverage_numerator", "coverage_denominator", "unsupported_numerator",
                "unsupported_hit_denominator", "unsupported_v_denominator",
            ):
                accumulator[key] += int(current[key])
            accumulator["absrel_chunks"].append(
                np.asarray(current["absrel_values"], dtype=np.float64)
            )
            accumulator["normal_angle_chunks"].append(
                np.asarray(current["normal_angle_values"], dtype=np.float64)
            )
            frame_counts[name].append(
                {
                    "numerator": int(current["coverage_numerator"]),
                    "denominator": int(current["coverage_denominator"]),
                }
            )
        shell = frame.get("double_shell", {})
        shell_eligible += int(shell.get("eligible_rays", 0))
        shell_events += int(shell.get("event_count", 0))
        shell_separations.extend(float(value) for value in shell.get("separations_mm", []))

    all_stats = accumulators["all"]
    metrics: dict[str, Any] = {}
    for name in subset_names:
        stats = accumulators[name]
        metrics[f"coverage_{name}"] = _fraction(
            stats["coverage_numerator"], stats["coverage_denominator"]
        )
    metrics.update(
        {
            "unsupported_over_hits": _fraction(
                all_stats["unsupported_numerator"], all_stats["unsupported_hit_denominator"]
            ),
            "unsupported_over_v": _fraction(
                all_stats["unsupported_numerator"], all_stats["unsupported_v_denominator"]
            ),
            "absrel_median_pp": _chunked_percentile(
                all_stats["absrel_chunks"], 0.5, 100.0
            ),
            "absrel_p95_pp": _chunked_percentile(
                all_stats["absrel_chunks"], 0.95, 100.0
            ),
            "normal_median_deg": _chunked_percentile(
                all_stats["normal_angle_chunks"], 0.5
            ),
            "double_shell_eligible_rays": shell_eligible,
            "double_shell_event_count": shell_events,
            "double_shell_rate": _fraction(shell_events, shell_eligible),
            "double_shell_p95_mm": _percentile(shell_separations, 0.95),
        }
    )
    return {"metrics": metrics, "frame_counts": frame_counts}


def paired_frame_bootstrap(
    baseline_counts: Sequence[Mapping[str, int]],
    candidate_counts: Sequence[Mapping[str, int]],
    *,
    replicates: int = 10_000,
    seed: int = 20260721,
) -> dict[str, Any]:
    """Paired frame bootstrap of candidate-minus-baseline coverage in pp."""

    if len(baseline_counts) != len(candidate_counts) or not baseline_counts:
        raise EvaluationContractError(METRIC_UNDEFINED, "paired frame lists differ or are empty")
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    bn = np.asarray([row["numerator"] for row in baseline_counts], dtype=np.int64)
    bd = np.asarray([row["denominator"] for row in baseline_counts], dtype=np.int64)
    cn = np.asarray([row["numerator"] for row in candidate_counts], dtype=np.int64)
    cd = np.asarray([row["denominator"] for row in candidate_counts], dtype=np.int64)
    if np.any(bn < 0) or np.any(cn < 0) or np.any(bd < bn) or np.any(cd < cn):
        raise EvaluationContractError(METRIC_UNDEFINED, "invalid frame count sums")
    if int(bd.sum()) == 0 or int(cd.sum()) == 0:
        raise EvaluationContractError(METRIC_UNDEFINED, "zero bootstrap denominator")
    estimate = (cn.sum() / cd.sum() - bn.sum() / bd.sum()) * 100.0
    rng = np.random.Generator(np.random.PCG64(seed))
    samples = np.empty(replicates, dtype=np.float64)
    frame_count = len(bn)
    # Chunking avoids allocating B x frame_count for a future full 413-frame gate.
    cursor = 0
    while cursor < replicates:
        take = min(1024, replicates - cursor)
        indices = rng.integers(0, frame_count, size=(take, frame_count))
        bden = bd[indices].sum(axis=1)
        cden = cd[indices].sum(axis=1)
        valid = (bden > 0) & (cden > 0)
        chunk = np.full(take, np.nan, dtype=np.float64)
        chunk[valid] = (
            cn[indices].sum(axis=1)[valid] / cden[valid]
            - bn[indices].sum(axis=1)[valid] / bden[valid]
        ) * 100.0
        samples[cursor:cursor + take] = chunk
        cursor += take
    finite = samples[np.isfinite(samples)]
    if not len(finite):
        raise EvaluationContractError(METRIC_UNDEFINED, "all bootstrap replicates undefined")
    return {
        "estimate_pp": float(estimate),
        "ci95_pp": [float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))],
        "replicates": int(replicates),
        "valid_replicates": int(len(finite)),
        "seed": int(seed),
        "rng": "PCG64",
    }


def _require_exact_contract_fields(
    supplied: Any, expected: Mapping[str, Any], *, label: str
) -> Mapping[str, Any]:
    if not isinstance(supplied, Mapping):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, f"{label} is missing or is not an object"
        )
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        actual = supplied.get(key)
        if isinstance(expected_value, bool):
            matches = actual is expected_value
        elif isinstance(expected_value, float):
            try:
                matches = float(actual).hex() == expected_value.hex()
            except (TypeError, ValueError):
                matches = False
        else:
            matches = actual == expected_value
        if not matches:
            mismatches.append(key)
    if mismatches:
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} differs from the frozen B0 prompt at {mismatches}",
        )
    return supplied


def preregistered_gate_profile(
    dataset_id: str, gate_contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate strict B0.6 gates supplied by the preregistration contract."""

    if not isinstance(dataset_id, str) or not dataset_id:
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            "dataset_id is empty or invalid",
        )
    _require_exact_contract_fields(
        gate_contract, STRICT_GATE_CONTRACT, label="preregistered noninferiority gates"
    )
    return {
        "name": "b0_prompt_strict",
        "dataset_id": dataset_id,
        "source": "preregistered_contract/strict_B0.6",
        "coverage_delta_pp_min": float(gate_contract["coverage_delta_min"]) * 100.0,
        "unsupported_delta_pp_max": float(
            gate_contract["unsupported_gt_20mm_delta_max"]
        ) * 100.0,
        "absrel_median_delta_pp_max": float(
            gate_contract["median_absrel_delta_max"]
        ) * 100.0,
        "absrel_p95_delta_pp_max": float(
            gate_contract["p95_absrel_delta_max"]
        ) * 100.0,
        "normal_median_delta_deg_max": float(
            gate_contract["median_normal_error_delta_max_deg"]
        ),
        "double_shell_rate_delta_pp_max": float(
            gate_contract["double_shell_rate_delta_max"]
        ) * 100.0,
        "double_shell_p95_delta_mm_max": float(
            gate_contract["double_shell_p95_separation_delta_max_m"]
        ) * 1000.0,
        "nonmanifold_ratio_max": float(
            gate_contract["nonmanifold_edge_fraction_max"]
        ),
        "require_double_shell": True,
        "finite_vertices_and_faces_required": True,
    }


def preregistered_improvement_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the only contract under which a final improvement verdict exists."""

    _require_exact_contract_fields(
        claim, STRICT_IMPROVEMENT_CONTRACT, label="preregistered improvement claim"
    )
    return {
        "bootstrap_replicates": int(claim["bootstrap_draws"]),
        "bootstrap_seed": int(claim["seed"]),
        "low_texture_lcb_pp_min": float(
            claim["required_low_texture_coverage_lower_bound"]
        ) * 100.0,
        "weak_support_lcb_pp_min": float(
            claim["required_weak_support_coverage_lower_bound"]
        ) * 100.0,
        "source": "preregistered_contract/improvement_claim",
    }


def decide_verdict(
    gate_summary: Mapping[str, Any], low_texture_lcb_pp: float, weak_support_lcb_pp: float
) -> dict[str, str]:
    if not gate_summary.get("required_metrics_defined", False):
        return {"verdict": "INCONCLUSIVE", "reason": "METRIC_UNDEFINED"}
    if not gate_summary.get("all_noninferiority_pass", False):
        return {"verdict": "FAIL", "reason": "NONINFERIORITY_FAILED"}
    if low_texture_lcb_pp >= 5.0 and weak_support_lcb_pp >= 5.0:
        return {"verdict": "PASS", "reason": "PROVEN_BETTER"}
    return {"verdict": "INCONCLUSIVE", "reason": "NOT_PROVEN_BETTER"}


def _delta(candidate: Any, baseline: Any, scale: float = 1.0) -> float | None:
    if candidate is None or baseline is None:
        return None
    values = np.asarray([candidate, baseline], dtype=np.float64)
    if not np.isfinite(values).all():
        return None
    return float((values[0] - values[1]) * scale)


def compare_route_evaluations(
    tsdf: Mapping[str, Any],
    fusecut: Mapping[str, Any],
    *,
    expected_digest: str,
    expected_evaluation_digest: str,
    dataset_id: str,
    split_id: str,
    coordinate_frame: str,
    metres_per_model_unit: float,
    input_contract_sha256: str,
    gate_contract: Mapping[str, Any],
    improvement_contract: Mapping[str, Any],
    bootstrap_replicates: int = 10_000,
    bootstrap_seed: int = 20260721,
) -> dict[str, Any]:
    """Compare routes after enforcing input, gate, frame, and scale identity."""

    profile = preregistered_gate_profile(dataset_id, gate_contract)
    improvement = preregistered_improvement_claim(improvement_contract)
    if (
        bootstrap_replicates != improvement["bootstrap_replicates"]
        or bootstrap_seed != improvement["bootstrap_seed"]
    ):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            "final verdict requires exactly 10000 paired draws with seed 20260721",
        )

    require_equivalent_route_inputs(
        expected_digest, str(tsdf.get("contract_digest", "")), str(fusecut.get("contract_digest", ""))
    )
    if not expected_evaluation_digest or not (
        tsdf.get("evaluation_digest")
        == expected_evaluation_digest
        == fusecut.get("evaluation_digest")
    ):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT,
            "held-out evaluation archive digests are not identical to the freeze",
        )
    require_matching_metric_unit_contracts(
        tsdf.get("unit_contract"),
        fusecut.get("unit_contract"),
        coordinate_frame=coordinate_frame,
        metres_per_model_unit=metres_per_model_unit,
        input_contract_sha256=input_contract_sha256,
        split_id=split_id,
    )
    if (
        tsdf.get("metric_scale") != "contract_model_units"
        or fusecut.get("metric_scale") != "contract_model_units"
    ):
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH,
            "both routes must declare contract_model_units",
        )
    if (
        tsdf.get("coordinate_frame") != coordinate_frame
        or fusecut.get("coordinate_frame") != coordinate_frame
        or tsdf.get("mesh_frame") != coordinate_frame
        or fusecut.get("mesh_frame") != coordinate_frame
    ):
        raise EvaluationContractError(
            COORDINATE_FRAME_MISMATCH,
            "both evaluated meshes must be in the shared contract coordinate frame",
        )
    tm, fm = tsdf.get("metrics", {}), fusecut.get("metrics", {})
    deltas = {
        "coverage_all_pp": _delta(fm.get("coverage_all"), tm.get("coverage_all"), 100.0),
        "coverage_low_texture_pp": _delta(
            fm.get("coverage_low_texture"), tm.get("coverage_low_texture"), 100.0
        ),
        "coverage_weak_support_pp": _delta(
            fm.get("coverage_weak_support"), tm.get("coverage_weak_support"), 100.0
        ),
        "unsupported_over_hits_pp": _delta(
            fm.get("unsupported_over_hits"), tm.get("unsupported_over_hits"), 100.0
        ),
        "absrel_median_pp": _delta(fm.get("absrel_median_pp"), tm.get("absrel_median_pp")),
        "absrel_p95_pp": _delta(fm.get("absrel_p95_pp"), tm.get("absrel_p95_pp")),
        "normal_median_deg": _delta(fm.get("normal_median_deg"), tm.get("normal_median_deg")),
        "double_shell_rate_pp": _delta(
            fm.get("double_shell_rate"), tm.get("double_shell_rate"), 100.0
        ),
        # With eligible rays but zero events, P95 is intentionally null and its
        # gate value is defined as zero.  No eligible primary ray is different:
        # that is an undefined metric and must remain inconclusive.
        "double_shell_p95_mm": _delta(
            (fm.get("double_shell_p95_mm") or 0.0)
            if fm.get("double_shell_rate") is not None else None,
            (tm.get("double_shell_p95_mm") or 0.0)
            if tm.get("double_shell_rate") is not None else None,
        ),
    }
    gates: dict[str, bool | None] = {
        "coverage_all": None if deltas["coverage_all_pp"] is None else deltas["coverage_all_pp"] >= profile["coverage_delta_pp_min"],
        "coverage_low_texture": None if deltas["coverage_low_texture_pp"] is None else deltas["coverage_low_texture_pp"] >= profile["coverage_delta_pp_min"],
        "coverage_weak_support": None if deltas["coverage_weak_support_pp"] is None else deltas["coverage_weak_support_pp"] >= profile["coverage_delta_pp_min"],
        "unsupported_over_hits": None if deltas["unsupported_over_hits_pp"] is None else deltas["unsupported_over_hits_pp"] <= profile["unsupported_delta_pp_max"],
        "absrel_median": None if deltas["absrel_median_pp"] is None else deltas["absrel_median_pp"] <= profile["absrel_median_delta_pp_max"],
        "absrel_p95": None if deltas["absrel_p95_pp"] is None else deltas["absrel_p95_pp"] <= profile["absrel_p95_delta_pp_max"],
        "normal_median": None if deltas["normal_median_deg"] is None else deltas["normal_median_deg"] <= profile["normal_median_delta_deg_max"],
    }
    if profile["require_double_shell"]:
        gates["double_shell_rate"] = (
            None if deltas["double_shell_rate_pp"] is None
            else deltas["double_shell_rate_pp"] <= profile["double_shell_rate_delta_pp_max"]
        )
        gates["double_shell_p95"] = (
            None if deltas["double_shell_p95_mm"] is None
            else deltas["double_shell_p95_mm"] <= profile["double_shell_p95_delta_mm_max"]
        )

    topology = fusecut.get("topology", {})
    finite = topology.get("finite") is True
    nm_ratio = topology.get("nonmanifold_edge_ratio")
    gates["finite"] = finite
    gates["nonmanifold"] = bool(
        nm_ratio is not None and np.isfinite(nm_ratio) and nm_ratio <= profile["nonmanifold_ratio_max"]
    )

    bootstrap: dict[str, Any] = {}
    metric_defined = all(value is not None for value in gates.values())
    for subset in ("low_texture", "weak_support", "union"):
        try:
            bootstrap[subset] = paired_frame_bootstrap(
                tsdf["frame_counts"][subset],
                fusecut["frame_counts"][subset],
                replicates=bootstrap_replicates,
                seed=bootstrap_seed,
            )
        except (KeyError, EvaluationContractError):
            bootstrap[subset] = None
            metric_defined = False
    gate_summary = {
        "required_metrics_defined": metric_defined,
        "all_noninferiority_pass": metric_defined and all(value is True for value in gates.values()),
    }
    low_lcb = bootstrap["low_texture"]["ci95_pp"][0] if bootstrap["low_texture"] else -math.inf
    weak_lcb = bootstrap["weak_support"]["ci95_pp"][0] if bootstrap["weak_support"] else -math.inf
    # The current prompt fixes both lower-bound thresholds at +5 pp.  Keep the
    # generic decision helper stable, while checking that the contract feeding
    # it actually contains those exact values above.
    if (
        improvement["low_texture_lcb_pp_min"] != 5.0
        or improvement["weak_support_lcb_pp_min"] != 5.0
    ):
        raise EvaluationContractError(
            ROUTE_INPUT_NOT_EQUIVALENT, "improvement lower-bound contract changed"
        )
    verdict = decide_verdict(gate_summary, low_lcb, weak_lcb)
    return {
        **verdict,
        "contract_digest": expected_digest,
        "evaluation_digest": expected_evaluation_digest,
        "dataset_id": dataset_id,
        "split_id": split_id,
        "controlled_variable": "mesher_only",
        "coordinate_frame": coordinate_frame,
        "metric_scale": "contract_model_units",
        "unit_contract": metric_unit_contract(
            coordinate_frame=coordinate_frame,
            metres_per_model_unit=metres_per_model_unit,
            input_contract_sha256=input_contract_sha256,
            split_id=split_id,
        ),
        "alignment": "none",
        "profile": profile,
        "improvement_contract": improvement,
        "deltas": deltas,
        "gates": gates,
        "gate_summary": gate_summary,
        "bootstrap": bootstrap,
    }
