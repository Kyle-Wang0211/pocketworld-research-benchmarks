#!/usr/bin/env python3
"""Generate Stage 02 official DA3 image-only camera geometry diagnostics."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont


STAGE02_DIR = Path(__file__).resolve().parent
EXP_ROOT = STAGE02_DIR.parent
RAW_DIR = EXP_ROOT / "01_stage01_official_depth_conf_photometric" / "raw_official_prediction_arrays"
REPORT_PATH = RAW_DIR / "window_000_commercial_safe_image_only_report.json"
SUSPECT_IDS = {"cap-74", "cap-78", "cap-80"}


def main() -> int:
    dirs = make_dirs()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    frame_ids = list(report["inputs"]["frame_ids"])

    depth = np.load(RAW_DIR / "pytorch_depth.npy").astype(np.float32)
    conf = np.load(RAW_DIR / "pytorch_conf.npy").astype(np.float32)
    images = np.load(RAW_DIR / "pytorch_processed_images.npy")
    intrinsics = np.load(RAW_DIR / "pytorch_intrinsics.npy").astype(np.float64)
    extrinsics = np.load(RAW_DIR / "pytorch_extrinsics.npy").astype(np.float64)

    if len(frame_ids) != intrinsics.shape[0] or len(frame_ids) != extrinsics.shape[0]:
        raise ValueError("frame count does not match intrinsics/extrinsics arrays")

    height, width = depth.shape[1], depth.shape[2]
    centers, axes = camera_centers_and_axes(extrinsics)
    intr_rows = build_intrinsics_rows(frame_ids, intrinsics, width, height)
    center_rows = build_center_rows(frame_ids, centers, axes)
    rel_rows = build_relative_rows(frame_ids, centers, axes, extrinsics)
    pair_rows, pair_baseline, pair_rot = build_pairwise_rows(frame_ids, centers, extrinsics)
    depth_rows = build_depth_pose_rows(frame_ids, depth, conf, centers)

    write_csv(dirs["tables"] / "stage02_intrinsics_per_frame.csv", intr_rows)
    write_csv(dirs["tables"] / "stage02_camera_centers_per_frame.csv", center_rows)
    write_csv(dirs["tables"] / "stage02_relative_pose_delta.csv", rel_rows)
    write_csv(dirs["tables"] / "stage02_pairwise_pose_metrics.csv", pair_rows)
    write_csv(dirs["tables"] / "stage02_depth_pose_context.csv", depth_rows)

    summary = summarize(frame_ids, intr_rows, center_rows, rel_rows, depth_rows, pair_baseline, pair_rot)
    (STAGE02_DIR / "stage02_camera_pose_geometry_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    plot_intrinsics(frame_ids, intr_rows, dirs["figures"])
    plot_center_components(frame_ids, centers, dirs["figures"])
    plot_pose_delta(frame_ids, rel_rows, dirs["figures"])
    plot_pairwise_heatmaps(frame_ids, pair_baseline, pair_rot, dirs["figures"])
    plot_camera_trajectory(frame_ids, centers, axes, dirs["figures"])
    plot_frustums(frame_ids, centers, axes, intrinsics, width, height, dirs["figures"])
    plot_depth_pose_panel(frame_ids, depth_rows, rel_rows, dirs["figures"])
    plot_matrix_heatmaps(frame_ids, intrinsics, extrinsics, dirs["matrix_heatmaps"])
    make_camera_cards(frame_ids, images, depth, conf, intrinsics, extrinsics, centers, axes, dirs["per_frame"])
    make_contact_sheets(dirs)
    write_results_readme(summary, dirs)
    write_visual_manifest(dirs, frame_ids)
    return 0


def make_dirs() -> dict[str, Path]:
    dirs = {
        "figures": STAGE02_DIR / "figures",
        "tables": STAGE02_DIR / "tables",
        "per_frame": STAGE02_DIR / "per_frame_camera_cards",
        "matrix_heatmaps": STAGE02_DIR / "matrix_heatmaps",
        "contact_sheets": STAGE02_DIR / "contact_sheets",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def camera_centers_and_axes(extrinsics: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    centers = []
    right = []
    down = []
    forward = []
    for ext in extrinsics:
        r = ext[:, :3]
        t = ext[:, 3]
        c = -r.T @ t
        centers.append(c)
        right.append(r.T @ np.array([1.0, 0.0, 0.0]))
        down.append(r.T @ np.array([0.0, 1.0, 0.0]))
        forward.append(r.T @ np.array([0.0, 0.0, 1.0]))
    return np.asarray(centers), {
        "right": normalize_rows(np.asarray(right)),
        "down": normalize_rows(np.asarray(down)),
        "forward": normalize_rows(np.asarray(forward)),
    }


def normalize_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def build_intrinsics_rows(frame_ids: list[str], k: np.ndarray, width: int, height: int) -> list[dict[str, float | int | str]]:
    rows = []
    for i, fid in enumerate(frame_ids):
        kk = k[i]
        fx, fy = float(kk[0, 0]), float(kk[1, 1])
        cx, cy = float(kk[0, 2]), float(kk[1, 2])
        fov_x = math.degrees(2.0 * math.atan((width * 0.5) / max(fx, 1e-9)))
        fov_y = math.degrees(2.0 * math.atan((height * 0.5) / max(fy, 1e-9)))
        rows.append(
            {
                "local_index": i,
                "frame_id": fid,
                "is_suspect": fid in SUSPECT_IDS,
                "fx": fx,
                "fy": fy,
                "cx": cx,
                "cy": cy,
                "fx_over_width": fx / width,
                "fy_over_height": fy / height,
                "cx_over_width": cx / width,
                "cy_over_height": cy / height,
                "fx_fy_ratio": fx / max(fy, 1e-9),
                "fov_x_deg": fov_x,
                "fov_y_deg": fov_y,
                "image_width": width,
                "image_height": height,
            }
        )
    return rows


def build_center_rows(frame_ids: list[str], centers: np.ndarray, axes: dict[str, np.ndarray]) -> list[dict[str, float | int | str]]:
    rows = []
    for i, fid in enumerate(frame_ids):
        rows.append(
            {
                "local_index": i,
                "frame_id": fid,
                "is_suspect": fid in SUSPECT_IDS,
                "center_x": float(centers[i, 0]),
                "center_y": float(centers[i, 1]),
                "center_z": float(centers[i, 2]),
                "forward_x": float(axes["forward"][i, 0]),
                "forward_y": float(axes["forward"][i, 1]),
                "forward_z": float(axes["forward"][i, 2]),
                "right_x": float(axes["right"][i, 0]),
                "right_y": float(axes["right"][i, 1]),
                "right_z": float(axes["right"][i, 2]),
                "down_x": float(axes["down"][i, 0]),
                "down_y": float(axes["down"][i, 1]),
                "down_z": float(axes["down"][i, 2]),
            }
        )
    return rows


def build_relative_rows(
    frame_ids: list[str],
    centers: np.ndarray,
    axes: dict[str, np.ndarray],
    extrinsics: np.ndarray,
) -> list[dict[str, float | int | str]]:
    rows = []
    for i in range(1, len(frame_ids)):
        r0 = extrinsics[i - 1, :, :3]
        r1 = extrinsics[i, :, :3]
        rot = r1 @ r0.T
        rows.append(
            {
                "transition_index": i - 1,
                "from_local_index": i - 1,
                "to_local_index": i,
                "from_frame_id": frame_ids[i - 1],
                "to_frame_id": frame_ids[i],
                "contains_suspect": frame_ids[i - 1] in SUSPECT_IDS or frame_ids[i] in SUSPECT_IDS,
                "center_distance": float(np.linalg.norm(centers[i] - centers[i - 1])),
                "dx": float(centers[i, 0] - centers[i - 1, 0]),
                "dy": float(centers[i, 1] - centers[i - 1, 1]),
                "dz": float(centers[i, 2] - centers[i - 1, 2]),
                "rotation_angle_deg": rotation_angle_deg(rot),
                "forward_angle_deg": vector_angle_deg(axes["forward"][i - 1], axes["forward"][i]),
                "right_angle_deg": vector_angle_deg(axes["right"][i - 1], axes["right"][i]),
                "down_angle_deg": vector_angle_deg(axes["down"][i - 1], axes["down"][i]),
            }
        )
    return rows


def build_pairwise_rows(
    frame_ids: list[str],
    centers: np.ndarray,
    extrinsics: np.ndarray,
) -> tuple[list[dict[str, float | int | str]], np.ndarray, np.ndarray]:
    n = len(frame_ids)
    baseline = np.zeros((n, n), dtype=np.float64)
    rot = np.zeros((n, n), dtype=np.float64)
    rows = []
    for i in range(n):
        for j in range(n):
            baseline[i, j] = np.linalg.norm(centers[j] - centers[i])
            rot_ij = extrinsics[j, :, :3] @ extrinsics[i, :, :3].T
            rot[i, j] = rotation_angle_deg(rot_ij)
            rows.append(
                {
                    "source_local_index": i,
                    "target_local_index": j,
                    "source_frame_id": frame_ids[i],
                    "target_frame_id": frame_ids[j],
                    "source_or_target_suspect": frame_ids[i] in SUSPECT_IDS or frame_ids[j] in SUSPECT_IDS,
                    "center_baseline": float(baseline[i, j]),
                    "rotation_angle_deg": float(rot[i, j]),
                }
            )
    return rows, baseline, rot


def build_depth_pose_rows(
    frame_ids: list[str],
    depth: np.ndarray,
    conf: np.ndarray,
    centers: np.ndarray,
) -> list[dict[str, float | int | str]]:
    rows = []
    prev = None
    for i, fid in enumerate(frame_ids):
        d = depth[i].reshape(-1)
        c = conf[i].reshape(-1)
        finite_d = d[np.isfinite(d)]
        finite_c = c[np.isfinite(c)]
        signal = np.maximum(finite_c - 1.0, 0.0)
        step = 0.0 if prev is None else float(np.linalg.norm(centers[i] - prev))
        prev = centers[i]
        rows.append(
            {
                "local_index": i,
                "frame_id": fid,
                "is_suspect": fid in SUSPECT_IDS,
                "depth_min": float(np.min(finite_d)),
                "depth_p10": float(np.percentile(finite_d, 10)),
                "depth_median": float(np.median(finite_d)),
                "depth_p90": float(np.percentile(finite_d, 90)),
                "depth_max": float(np.max(finite_d)),
                "depth_std": float(np.std(finite_d)),
                "conf_min": float(np.min(finite_c)),
                "conf_median": float(np.median(finite_c)),
                "conf_mean": float(np.mean(finite_c)),
                "conf_signal_mean": float(np.mean(signal)),
                "conf_signal_p90": float(np.percentile(signal, 90)),
                "adjacent_center_step": step,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(
    frame_ids: list[str],
    intr_rows: list[dict[str, object]],
    center_rows: list[dict[str, object]],
    rel_rows: list[dict[str, object]],
    depth_rows: list[dict[str, object]],
    pair_baseline: np.ndarray,
    pair_rot: np.ndarray,
) -> dict[str, object]:
    def vals(rows: list[dict[str, object]], key: str) -> np.ndarray:
        return np.asarray([float(r[key]) for r in rows], dtype=np.float64)

    center_distance = vals(rel_rows, "center_distance")
    rot_delta = vals(rel_rows, "rotation_angle_deg")
    fwd_delta = vals(rel_rows, "forward_angle_deg")
    fx = vals(intr_rows, "fx")
    fy = vals(intr_rows, "fy")
    cx = vals(intr_rows, "cx")
    cy = vals(intr_rows, "cy")
    depth_median = vals(depth_rows, "depth_median")
    conf_signal = vals(depth_rows, "conf_signal_mean")

    return {
        "schema_version": "aether_da3_stage02_camera_pose_geometry_audit_v1",
        "purpose": "Visualize and audit DA3 image-only predicted intrinsics/extrinsics before any pointcloud or fusion step.",
        "frame_count": len(frame_ids),
        "frame_ids": frame_ids,
        "suspect_frame_ids": sorted(SUSPECT_IDS),
        "outputs": {
            "tables_dir": str(STAGE02_DIR / "tables"),
            "figures_dir": str(STAGE02_DIR / "figures"),
            "per_frame_camera_cards_dir": str(STAGE02_DIR / "per_frame_camera_cards"),
            "matrix_heatmaps_dir": str(STAGE02_DIR / "matrix_heatmaps"),
            "contact_sheets_dir": str(STAGE02_DIR / "contact_sheets"),
        },
        "intrinsics_summary": {
            "fx_min": float(fx.min()),
            "fx_max": float(fx.max()),
            "fx_range": float(fx.max() - fx.min()),
            "fy_min": float(fy.min()),
            "fy_max": float(fy.max()),
            "fy_range": float(fy.max() - fy.min()),
            "cx_min": float(cx.min()),
            "cx_max": float(cx.max()),
            "cy_min": float(cy.min()),
            "cy_max": float(cy.max()),
        },
        "pose_delta_summary": {
            "center_distance_median": float(np.median(center_distance)),
            "center_distance_p90": float(np.percentile(center_distance, 90)),
            "center_distance_max": float(center_distance.max()),
            "rotation_delta_median_deg": float(np.median(rot_delta)),
            "rotation_delta_p90_deg": float(np.percentile(rot_delta, 90)),
            "rotation_delta_max_deg": float(rot_delta.max()),
            "forward_delta_median_deg": float(np.median(fwd_delta)),
            "forward_delta_p90_deg": float(np.percentile(fwd_delta, 90)),
            "forward_delta_max_deg": float(fwd_delta.max()),
        },
        "pairwise_summary": {
            "baseline_min_nonzero": float(pair_baseline[pair_baseline > 0].min()),
            "baseline_max": float(pair_baseline.max()),
            "rotation_angle_max_deg": float(pair_rot.max()),
        },
        "depth_conf_context_summary": {
            "depth_median_min": float(depth_median.min()),
            "depth_median_max": float(depth_median.max()),
            "conf_signal_mean_min": float(conf_signal.min()),
            "conf_signal_mean_max": float(conf_signal.max()),
        },
        "top_center_distance_transitions": top_rows(rel_rows, "center_distance", 5),
        "top_rotation_delta_transitions": top_rows(rel_rows, "rotation_angle_deg", 5),
        "suspect_frame_context": [
            {
                "frame_id": fid,
                "local_index": frame_ids.index(fid),
                "intrinsics": intr_rows[frame_ids.index(fid)],
                "center": center_rows[frame_ids.index(fid)],
                "depth_conf": depth_rows[frame_ids.index(fid)],
            }
            for fid in frame_ids
            if fid in SUSPECT_IDS
        ],
    }


def top_rows(rows: list[dict[str, object]], key: str, n: int) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: float(row[key]), reverse=True)[:n]


def rotation_angle_deg(rot: np.ndarray) -> float:
    trace = float(np.trace(rot))
    cos = max(-1.0, min(1.0, (trace - 1.0) * 0.5))
    return math.degrees(math.acos(cos))


def vector_angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    cos = float(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def x_labels(frame_ids: list[str]) -> list[str]:
    return [f"{i}\n{fid}" for i, fid in enumerate(frame_ids)]


def mark_suspects(ax, frame_ids: list[str], y_text: bool = False) -> None:
    for i, fid in enumerate(frame_ids):
        if fid in SUSPECT_IDS:
            ax.axvspan(i - 0.35, i + 0.35, color="#ff7f0e", alpha=0.18, linewidth=0)
            if y_text:
                ax.text(i, ax.get_ylim()[1], fid, rotation=90, va="top", ha="center", fontsize=7, color="#9a4b00")


def plot_intrinsics(frame_ids: list[str], rows: list[dict[str, object]], fig_dir: Path) -> None:
    x = np.arange(len(frame_ids))
    keys = ["fx", "fy", "cx", "cy", "fov_x_deg", "fov_y_deg"]
    fig, axes = plt.subplots(3, 2, figsize=(17, 12), constrained_layout=True)
    for ax, key in zip(axes.ravel(), keys):
        y = np.asarray([float(row[key]) for row in rows])
        ax.plot(x, y, marker="o", linewidth=1.5)
        mark_suspects(ax, frame_ids)
        ax.set_title(key)
        ax.grid(True, alpha=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels(frame_ids), rotation=75, fontsize=6)
    fig.suptitle("Stage 02 Intrinsics Timeseries", fontsize=16)
    fig.savefig(fig_dir / "stage02_intrinsics_timeseries.png", dpi=180)
    plt.close(fig)

    norm_keys = ["fx_over_width", "fy_over_height", "cx_over_width", "cy_over_height", "fx_fy_ratio"]
    fig, axes = plt.subplots(3, 2, figsize=(17, 12), constrained_layout=True)
    for ax, key in zip(axes.ravel(), norm_keys):
        y = np.asarray([float(row[key]) for row in rows])
        ax.plot(x, y, marker="o", linewidth=1.5)
        mark_suspects(ax, frame_ids)
        ax.set_title(key)
        ax.grid(True, alpha=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels(frame_ids), rotation=75, fontsize=6)
    axes.ravel()[-1].axis("off")
    fig.suptitle("Stage 02 Normalized Intrinsics", fontsize=16)
    fig.savefig(fig_dir / "stage02_intrinsics_normalized_timeseries.png", dpi=180)
    plt.close(fig)


def plot_center_components(frame_ids: list[str], centers: np.ndarray, fig_dir: Path) -> None:
    x = np.arange(len(frame_ids))
    fig, axes = plt.subplots(3, 1, figsize=(17, 10), constrained_layout=True)
    for ax, idx, name in zip(axes, range(3), ["center_x", "center_y", "center_z"]):
        ax.plot(x, centers[:, idx], marker="o", linewidth=1.5)
        mark_suspects(ax, frame_ids)
        ax.set_title(name)
        ax.grid(True, alpha=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels(frame_ids), rotation=75, fontsize=6)
    fig.suptitle("Stage 02 Camera Center Components", fontsize=16)
    fig.savefig(fig_dir / "stage02_camera_center_components.png", dpi=180)
    plt.close(fig)


def plot_pose_delta(frame_ids: list[str], rows: list[dict[str, object]], fig_dir: Path) -> None:
    x = np.arange(1, len(frame_ids))
    keys = ["center_distance", "rotation_angle_deg", "forward_angle_deg", "right_angle_deg", "down_angle_deg"]
    fig, axes = plt.subplots(3, 2, figsize=(17, 12), constrained_layout=True)
    for ax, key in zip(axes.ravel(), keys):
        y = np.asarray([float(row[key]) for row in rows])
        ax.plot(x, y, marker="o", linewidth=1.5)
        mark_suspects(ax, frame_ids)
        ax.set_title(key)
        ax.grid(True, alpha=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels(frame_ids)[1:], rotation=75, fontsize=6)
    axes.ravel()[-1].axis("off")
    fig.suptitle("Stage 02 Adjacent Pose Delta Timeseries", fontsize=16)
    fig.savefig(fig_dir / "stage02_pose_delta_timeseries.png", dpi=180)
    plt.close(fig)


def plot_pairwise_heatmaps(frame_ids: list[str], baseline: np.ndarray, rot: np.ndarray, fig_dir: Path) -> None:
    for name, arr, cbar in [
        ("stage02_pairwise_baseline_heatmap.png", baseline, "camera center distance"),
        ("stage02_pairwise_rotation_heatmap.png", rot, "rotation angle deg"),
    ]:
        fig, ax = plt.subplots(figsize=(13, 11), constrained_layout=True)
        im = ax.imshow(arr, cmap="magma")
        ax.set_title(cbar)
        ax.set_xlabel("target frame")
        ax.set_ylabel("source frame")
        ax.set_xticks(np.arange(len(frame_ids)))
        ax.set_yticks(np.arange(len(frame_ids)))
        ax.set_xticklabels(x_labels(frame_ids), rotation=75, fontsize=6)
        ax.set_yticklabels(x_labels(frame_ids), fontsize=6)
        for i, fid in enumerate(frame_ids):
            if fid in SUSPECT_IDS:
                ax.axhline(i, color="cyan", linewidth=0.8, alpha=0.7)
                ax.axvline(i, color="cyan", linewidth=0.8, alpha=0.7)
        fig.colorbar(im, ax=ax, shrink=0.75)
        fig.savefig(fig_dir / name, dpi=180)
        plt.close(fig)


def plot_camera_trajectory(frame_ids: list[str], centers: np.ndarray, axes: dict[str, np.ndarray], fig_dir: Path) -> None:
    pairs = [(0, 2, "top: X/Z"), (0, 1, "front: X/Y"), (2, 1, "side: Z/Y")]
    fig, axs = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    for ax, (a, b, title) in zip(axs, pairs):
        ax.plot(centers[:, a], centers[:, b], "-o", linewidth=1.3, markersize=4)
        for i, fid in enumerate(frame_ids):
            color = "#ff7f0e" if fid in SUSPECT_IDS else "#1f77b4"
            ax.scatter([centers[i, a]], [centers[i, b]], color=color, s=32)
            ax.text(centers[i, a], centers[i, b], str(i), fontsize=7)
            q = axes["forward"][i]
            ax.arrow(centers[i, a], centers[i, b], q[a] * 0.015, q[b] * 0.015, head_width=0.004, color=color, alpha=0.7)
        ax.set_title(title)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, alpha=0.25)
    fig.suptitle("Stage 02 Camera Trajectory Top / Front / Side", fontsize=16)
    fig.savefig(fig_dir / "stage02_camera_trajectory_top_front_side.png", dpi=180)
    plt.close(fig)

    fig = plt.figure(figsize=(12, 10), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(centers[:, 0], centers[:, 1], centers[:, 2], "-o", linewidth=1.2, markersize=4)
    for i, fid in enumerate(frame_ids):
        color = "#ff7f0e" if fid in SUSPECT_IDS else "#1f77b4"
        ax.scatter(centers[i, 0], centers[i, 1], centers[i, 2], color=color, s=32)
        ax.text(centers[i, 0], centers[i, 1], centers[i, 2], f"{i}", fontsize=7)
        f = axes["forward"][i] * 0.02
        ax.quiver(centers[i, 0], centers[i, 1], centers[i, 2], f[0], f[1], f[2], color=color, length=1.0, normalize=False)
    ax.set_title("Stage 02 Camera Trajectory 3D")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    set_axes_equal(ax)
    fig.savefig(fig_dir / "stage02_camera_trajectory_3d.png", dpi=180)
    plt.close(fig)


def plot_frustums(
    frame_ids: list[str],
    centers: np.ndarray,
    axes: dict[str, np.ndarray],
    intrinsics: np.ndarray,
    width: int,
    height: int,
    fig_dir: Path,
) -> None:
    span = max(float(np.ptp(centers[:, 0])), float(np.ptp(centers[:, 1])), float(np.ptp(centers[:, 2])), 1e-3)
    depth_scale = span * 0.12
    fig = plt.figure(figsize=(14, 12), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(centers[:, 0], centers[:, 1], centers[:, 2], color="#333333", linewidth=1.0)
    for i, fid in enumerate(frame_ids):
        color = "#ff7f0e" if fid in SUSPECT_IDS else plt.cm.viridis(i / max(1, len(frame_ids) - 1))
        corners = frustum_corners_world(centers[i], axes, i, intrinsics[i], width, height, depth_scale)
        c = centers[i]
        ax.scatter(c[0], c[1], c[2], color=color, s=20)
        for p in corners:
            ax.plot([c[0], p[0]], [c[1], p[1]], [c[2], p[2]], color=color, linewidth=0.6, alpha=0.75)
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            pa, pb = corners[a], corners[b]
            ax.plot([pa[0], pb[0]], [pa[1], pb[1]], [pa[2], pb[2]], color=color, linewidth=0.7, alpha=0.9)
        ax.text(c[0], c[1], c[2], str(i), fontsize=6)
    ax.set_title("Stage 02 Camera Frustums In DA3 World Space")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    set_axes_equal(ax)
    fig.savefig(fig_dir / "stage02_camera_frustums_world.png", dpi=180)
    plt.close(fig)


def frustum_corners_world(
    center: np.ndarray,
    axes: dict[str, np.ndarray],
    i: int,
    k: np.ndarray,
    width: int,
    height: int,
    z: float,
) -> np.ndarray:
    fx, fy, cx, cy = k[0, 0], k[1, 1], k[0, 2], k[1, 2]
    pix = [(0, 0), (width, 0), (width, height), (0, height)]
    out = []
    right = axes["right"][i]
    down = axes["down"][i]
    forward = axes["forward"][i]
    for u, v in pix:
        x = (u - cx) / max(fx, 1e-9) * z
        y = (v - cy) / max(fy, 1e-9) * z
        out.append(center + right * x + down * y + forward * z)
    return np.asarray(out)


def plot_depth_pose_panel(frame_ids: list[str], depth_rows: list[dict[str, object]], rel_rows: list[dict[str, object]], fig_dir: Path) -> None:
    x = np.arange(len(frame_ids))
    step = np.asarray([float(row["adjacent_center_step"]) for row in depth_rows])
    keys = ["depth_median", "depth_p90", "conf_signal_mean", "conf_signal_p90", "adjacent_center_step"]
    fig, axes = plt.subplots(3, 2, figsize=(17, 12), constrained_layout=True)
    for ax, key in zip(axes.ravel(), keys):
        y = np.asarray([float(row[key]) for row in depth_rows])
        ax.plot(x, y, marker="o", linewidth=1.5)
        mark_suspects(ax, frame_ids)
        ax.set_title(key)
        ax.grid(True, alpha=0.25)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels(frame_ids), rotation=75, fontsize=6)
    axes.ravel()[-1].scatter(step, [float(row["depth_median"]) for row in depth_rows], s=35)
    for i, fid in enumerate(frame_ids):
        color = "#ff7f0e" if fid in SUSPECT_IDS else "#333333"
        axes.ravel()[-1].text(step[i], float(depth_rows[i]["depth_median"]), str(i), fontsize=7, color=color)
    axes.ravel()[-1].set_title("depth_median vs adjacent_center_step")
    axes.ravel()[-1].set_xlabel("adjacent center step")
    axes.ravel()[-1].set_ylabel("depth median")
    axes.ravel()[-1].grid(True, alpha=0.25)
    fig.suptitle("Stage 02 Depth / Confidence / Pose Context", fontsize=16)
    fig.savefig(fig_dir / "stage02_depth_pose_scale_panel.png", dpi=180)
    plt.close(fig)


def plot_matrix_heatmaps(frame_ids: list[str], intrinsics: np.ndarray, extrinsics: np.ndarray, out_dir: Path) -> None:
    for name, arr, cmap in [
        ("stage02_intrinsics_matrix_heatmap_contact.png", intrinsics, "viridis"),
        ("stage02_extrinsics_matrix_heatmap_contact.png", extrinsics, "coolwarm"),
    ]:
        n = len(frame_ids)
        cols = 5
        rows = math.ceil(n / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.0, rows * 2.4), constrained_layout=True)
        axes_flat = axes.ravel()
        vmin = float(np.percentile(arr, 2))
        vmax = float(np.percentile(arr, 98))
        for i in range(rows * cols):
            ax = axes_flat[i]
            if i >= n:
                ax.axis("off")
                continue
            im = ax.imshow(arr[i], cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_title(f"{i} {frame_ids[i]}", fontsize=8, color="#b45a00" if frame_ids[i] in SUSPECT_IDS else "black")
            ax.set_xticks([])
            ax.set_yticks([])
            for yy in range(arr[i].shape[0]):
                for xx in range(arr[i].shape[1]):
                    ax.text(xx, yy, f"{arr[i, yy, xx]:.2f}", ha="center", va="center", fontsize=6, color="white")
        fig.suptitle(name.replace("_", " ").replace(".png", ""), fontsize=16)
        fig.colorbar(im, ax=axes_flat.tolist(), shrink=0.55)
        fig.savefig(out_dir / name, dpi=180)
        plt.close(fig)


def make_camera_cards(
    frame_ids: list[str],
    images: np.ndarray,
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    centers: np.ndarray,
    axes: dict[str, np.ndarray],
    out_dir: Path,
) -> None:
    font = ImageFont.load_default()
    for i, fid in enumerate(frame_ids):
        canvas = Image.new("RGB", (1100, 720), "white")
        draw = ImageDraw.Draw(canvas)
        color = (210, 90, 0) if fid in SUSPECT_IDS else (30, 30, 30)
        draw.text((24, 20), f"Stage 02 Camera Card | local {i:02d} | {fid}", fill=color, font=font)
        rgb = Image.fromarray(images[i]).resize((504, 280), Image.Resampling.BICUBIC)
        canvas.paste(rgb, (24, 58))
        d_img = normalize_image(depth[i]).resize((252, 140), Image.Resampling.BICUBIC).convert("RGB")
        c_img = normalize_image(np.maximum(conf[i] - 1.0, 0.0)).resize((252, 140), Image.Resampling.BICUBIC).convert("RGB")
        canvas.paste(d_img, (24, 370))
        canvas.paste(c_img, (292, 370))
        draw.text((24, 350), "depth normalized", fill=(0, 0, 0), font=font)
        draw.text((292, 350), "confidence signal conf-1", fill=(0, 0, 0), font=font)

        kk = intrinsics[i]
        ext = extrinsics[i]
        lines = [
            "Intrinsics K",
            f"fx={kk[0,0]:.6f}  fy={kk[1,1]:.6f}",
            f"cx={kk[0,2]:.6f}  cy={kk[1,2]:.6f}",
            f"fx/fy={kk[0,0]/max(kk[1,1],1e-9):.6f}",
            "",
            "Camera center C = -R^T t",
            f"x={centers[i,0]: .8f}",
            f"y={centers[i,1]: .8f}",
            f"z={centers[i,2]: .8f}",
            "",
            "Forward axis in world",
            f"x={axes['forward'][i,0]: .8f}",
            f"y={axes['forward'][i,1]: .8f}",
            f"z={axes['forward'][i,2]: .8f}",
            "",
            "Raw w2c extrinsics [R|t]",
        ]
        y = 60
        for line in lines:
            draw.text((580, y), line, fill=(0, 0, 0), font=font)
            y += 22
        for row in range(3):
            draw.text(
                (580, y),
                " ".join(f"{ext[row, col]: .6f}" for col in range(4)),
                fill=(0, 0, 0),
                font=font,
            )
            y += 22

        draw_mini_trajectory(draw, centers, i, origin=(600, 535), size=(360, 150), frame_ids=frame_ids)
        canvas.save(out_dir / f"{i:02d}_{fid}_camera_card.png")


def normalize_image(arr: np.ndarray) -> Image.Image:
    x = np.asarray(arr, dtype=np.float64)
    lo, hi = np.nanpercentile(x, [2, 98])
    y = np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1)
    return Image.fromarray(np.uint8(y * 255))


def draw_mini_trajectory(draw: ImageDraw.ImageDraw, centers: np.ndarray, current: int, origin: tuple[int, int], size: tuple[int, int], frame_ids: list[str]) -> None:
    x0, y0 = origin
    w, h = size
    xs = centers[:, 0]
    zs = centers[:, 2]
    pad = 8
    xmin, xmax = float(xs.min()), float(xs.max())
    zmin, zmax = float(zs.min()), float(zs.max())
    sx = (w - 2 * pad) / max(xmax - xmin, 1e-9)
    sz = (h - 2 * pad) / max(zmax - zmin, 1e-9)

    def p(idx: int) -> tuple[float, float]:
        return x0 + pad + (xs[idx] - xmin) * sx, y0 + h - pad - (zs[idx] - zmin) * sz

    draw.rectangle((x0, y0, x0 + w, y0 + h), outline=(180, 180, 180))
    draw.text((x0, y0 - 16), "mini trajectory X/Z", fill=(0, 0, 0), font=ImageFont.load_default())
    for i in range(1, len(xs)):
        draw.line((*p(i - 1), *p(i)), fill=(110, 110, 110), width=1)
    for i, fid in enumerate(frame_ids):
        px, py = p(i)
        fill = (230, 100, 0) if fid in SUSPECT_IDS else (60, 120, 200)
        if i == current:
            fill = (220, 0, 0)
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=fill)
        if i == current:
            draw.text((px + 5, py - 5), str(i), fill=(220, 0, 0), font=ImageFont.load_default())


def make_contact_sheets(dirs: dict[str, Path]) -> None:
    figure_files = sorted(dirs["figures"].glob("*.png")) + sorted(dirs["matrix_heatmaps"].glob("*.png"))
    make_image_grid(figure_files, dirs["contact_sheets"] / "stage02_all_figures_contact_sheet.png", tile_w=420, tile_h=300, cols=3)
    card_files = sorted(dirs["per_frame"].glob("*_camera_card.png"))
    make_image_grid(card_files, dirs["contact_sheets"] / "stage02_per_frame_camera_cards_contact_sheet.jpg", tile_w=330, tile_h=216, cols=5)


def make_image_grid(files: list[Path], out: Path, tile_w: int, tile_h: int, cols: int) -> None:
    if not files:
        return
    rows = math.ceil(len(files) / cols)
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, path in enumerate(files):
        im = Image.open(path).convert("RGB")
        im.thumbnail((tile_w, tile_h - 18), Image.Resampling.LANCZOS)
        x = (idx % cols) * tile_w
        y = (idx // cols) * tile_h
        sheet.paste(im, (x + (tile_w - im.width) // 2, y + 18))
        draw.text((x + 4, y + 3), path.name, fill=(0, 0, 0), font=font)
    sheet.save(out, quality=92)


def write_results_readme(summary: dict[str, object], dirs: dict[str, Path]) -> None:
    pose = summary["pose_delta_summary"]
    intr = summary["intrinsics_summary"]
    text = f"""# Stage 02 Results

Stage 02 visualizes DA3 image-only predicted camera geometry before pointcloud, Sim3, loop graph, or fusion.

## Key Numbers

- frame count: `{summary['frame_count']}`
- suspect frames: `{', '.join(summary['suspect_frame_ids'])}`
- fx range: `{intr['fx_range']:.6f}`
- fy range: `{intr['fy_range']:.6f}`
- adjacent center distance median / p90 / max: `{pose['center_distance_median']:.6f}` / `{pose['center_distance_p90']:.6f}` / `{pose['center_distance_max']:.6f}`
- adjacent rotation median / p90 / max: `{pose['rotation_delta_median_deg']:.6f}` / `{pose['rotation_delta_p90_deg']:.6f}` / `{pose['rotation_delta_max_deg']:.6f}` degrees

## Outputs

- tables: `tables/`
- figures: `figures/`
- per-frame camera cards: `per_frame_camera_cards/`
- matrix heatmaps: `matrix_heatmaps/`
- contact sheets: `contact_sheets/`
- JSON report: `stage02_camera_pose_geometry_report.json`

## How To Read

- Trajectory figures show where DA3 thinks each camera is.
- Frustum figure shows each camera's viewing pyramid in DA3 world space.
- Intrinsics curves show whether focal length and principal point jump between frames.
- Pose delta curves show adjacent-frame camera jumps.
- Pairwise baseline heatmap shows distance between every pair of predicted camera centers.
- Matrix heatmaps show the raw K and w2c extrinsic matrices for all 35 frames.
"""
    (STAGE02_DIR / "README_STAGE02_RESULTS_ZH.md").write_text(text, encoding="utf-8")


def write_visual_manifest(dirs: dict[str, Path], frame_ids: list[str]) -> None:
    payload = {
        "schema_version": "aether_da3_stage02_visual_manifest_v1",
        "frame_ids": frame_ids,
        "figures": [str(p) for p in sorted(dirs["figures"].glob("*.png"))],
        "contact_sheets": [str(p) for p in sorted(dirs["contact_sheets"].glob("*"))],
        "matrix_heatmaps": [str(p) for p in sorted(dirs["matrix_heatmaps"].glob("*.png"))],
        "per_frame_camera_cards": [str(p) for p in sorted(dirs["per_frame"].glob("*.png"))],
        "tables": [str(p) for p in sorted(dirs["tables"].glob("*.csv"))],
    }
    (STAGE02_DIR / "stage02_visual_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def set_axes_equal(ax) -> None:
    x_limits = ax.get_xlim3d()
    y_limits = ax.get_ylim3d()
    z_limits = ax.get_zlim3d()
    x_range = abs(x_limits[1] - x_limits[0])
    y_range = abs(y_limits[1] - y_limits[0])
    z_range = abs(z_limits[1] - z_limits[0])
    max_range = max(x_range, y_range, z_range)
    x_mid = np.mean(x_limits)
    y_mid = np.mean(y_limits)
    z_mid = np.mean(z_limits)
    ax.set_xlim3d([x_mid - max_range / 2, x_mid + max_range / 2])
    ax.set_ylim3d([y_mid - max_range / 2, y_mid + max_range / 2])
    ax.set_zlim3d([z_mid - max_range / 2, z_mid + max_range / 2])


if __name__ == "__main__":
    raise SystemExit(main())
