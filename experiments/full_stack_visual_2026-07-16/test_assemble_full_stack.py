#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import math
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assemble_full_stack as subject


def rotation_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.asarray([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def write_ascii_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray, extra: bool = False) -> None:
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(xyz)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
    ]
    if extra:
        lines.append("property float zncc_median")
    lines.append("end_header")
    for point, colour in zip(xyz, rgb):
        row = [*(f"{value:.12g}" for value in point), *(str(int(value)) for value in colour)]
        if extra:
            row.append("0.91")
        lines.append(" ".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_pose_inputs(device_meta: Path, replay_csv: Path, source_centres: np.ndarray, target_centres: np.ndarray) -> None:
    poses = []
    with replay_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frame_id", "registered", "qw", "qx", "qy", "qz", "tx", "ty", "tz"])
        for index, (source, target) in enumerate(zip(source_centres, target_centres)):
            # Identity world-to-camera rotation means tvec = -camera_center.
            writer.writerow([index, 1, 1, 0, 0, 0, *(-source)])
            poses.append(
                {
                    "frame_id": index,
                    "registered": True,
                    "quat_wxyz": [1, 0, 0, 0],
                    "t": (-target).tolist(),
                }
            )
    device_meta.write_text(json.dumps({"schema": "test", "poses": poses}), encoding="utf-8")


class FullStackAssemblerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _args(self, **overrides) -> Namespace:
        values = dict(
            device_sparse=str(self.root / "device.ply"),
            device_meta=str(self.root / "device.json"),
            ghost_sparse=str(self.root / "ghost.ply"),
            ghost_poses=str(self.root / "poses.csv"),
            replay_ledger=str(self.root / "ledger.jsonl"),
            replay_to_metric_manifest=None,
            metric_to_raw_manifest=None,
            b_floor=[str(self.root / "floor.ply")],
            b_floor_gauge=["device_raw"],
            b_wall=[str(self.root / "wall.ply")],
            b_wall_gauge=["device_raw"],
            d_cloud=[str(self.root / "d.ply")],
            d_cloud_gauge=["device_raw"],
            require_b_floor=True,
            require_b_wall=True,
            require_d=True,
            strict_final=False,
            review_classification="unclassified",
            known_limitation=[],
            capture_name="cap41",
            ghost_provenance_json=None,
            b_floor_provenance_json=[],
            b_wall_provenance_json=[],
            d_certificate_json=None,
            d_asset_inventory_json=None,
            registration_exception_json=None,
            ghost_env=["AETHER_GHOST_GATE=1", "AETHER_GHOST_MIN_VIEWS=3", "AETHER_GHOST_DEPTH_CONFLICT=1"],
            c_backend="wgsl_tiled_24x17_sha256:test",
            c_backend_json=None,
            device_translation="tvec",
            replay_translation="tvec",
            expected_registered=12,
            expected_frame_count=12,
            output_ply=str(self.root / "full.ply"),
            output_manifest=str(self.root / "manifest.json"),
        )
        values.update(overrides)
        return Namespace(**values)

    def _fixture(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rng = np.random.default_rng(91)
        source_centres = rng.normal(size=(12, 3))
        rotation = rotation_z(0.37)
        scale = 2.75
        translation = np.asarray([4.0, -3.0, 1.25])
        target_centres = scale * (source_centres @ rotation.T) + translation
        # One corresponding pose is corrupt; robust fitting must reject it.
        target_centres[7] += np.asarray([80.0, -20.0, 15.0])
        write_pose_inputs(self.root / "device.json", self.root / "poses.csv", source_centres, target_centres)
        (self.root / "ledger.jsonl").write_text(
            "".join(json.dumps({"frameId": index}) + "\n" for index in range(12)),
            encoding="utf-8",
        )

        ghost_xyz = rng.normal(size=(5, 3))
        ghost_rgb = np.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12], [13, 14, 15]], dtype=np.uint8)
        aligned_ghost_xyz = scale * (ghost_xyz @ rotation.T) + translation
        device_xyz = np.vstack([aligned_ghost_xyz, aligned_ghost_xyz[:4] + 0.01])
        device_rgb = np.vstack([ghost_rgb, ghost_rgb[:4]])
        write_ascii_ply(self.root / "device.ply", device_xyz, device_rgb)
        write_ascii_ply(self.root / "ghost.ply", ghost_xyz, ghost_rgb)
        write_ascii_ply(self.root / "floor.ply", np.asarray([[20.0, 21.0, 22.0]]), np.asarray([[20, 21, 22]]), True)
        write_ascii_ply(self.root / "wall.ply", np.asarray([[30.0, 31.0, 32.0]]), np.asarray([[30, 31, 32]]))
        write_ascii_ply(self.root / "d.ply", np.asarray([[40.0, 41.0, 42.0]]), np.asarray([[40, 41, 42]]))
        return ghost_xyz, ghost_rgb, rotation, translation

    def _valid_strict_args(self, capture_name: str = "cap41") -> Namespace:
        hashes = {name: subject.sha256_file(self.root / name) for name in ("ghost.ply", "floor.ply", "wall.ply", "d.ply")}
        ghost = subject.read_rgb_ply(self.root / "ghost.ply")
        c_artifact = self.root / "libaether_test.dylib"
        c_artifact.write_bytes(b"pinned-c-backend")
        c_source = self.root / "tiled_reference.wgsl"
        c_source.write_text("@compute @workgroup_size(24, 17, 1) fn main() {}\n", encoding="utf-8")
        c_execution_report = {
            "schema": "pw_c_tiled_execution_report_v1",
            "status": "PASS",
            "backend": "cross_platform_tiled_reference",
            "backend_exercised": True,
            "backend_artifact_sha256": subject.sha256_file(c_artifact),
            "executions": [
                {
                    "algorithm_role": "known_plane_b_floor",
                    "effective_parameters": {"tile_points": 128},
                    "input_identity": {"sha256": hashes["ghost.ply"]},
                    "output_identity": {"sha256": hashes["floor.ply"]},
                    "output_validation": {
                        "exact": True,
                        "mismatch_count": 0,
                        "max_abs_error": 0.0,
                    },
                    "elapsed_ms": 1.25,
                    "peak_memory_bytes": 4096,
                },
                {
                    "algorithm_role": "known_plane_b_wall",
                    "effective_parameters": {"tile_points": 64},
                    "input_identity": {"sha256": hashes["ghost.ply"]},
                    "output_identity": {"sha256": hashes["wall.ply"]},
                    "output_validation": {
                        "exact": True,
                        "mismatch_count": 0,
                        "max_abs_error": 0.0,
                    },
                    "elapsed_ms": 1.0,
                    "peak_memory_bytes": 2048,
                },
            ],
            "source_artifacts": [
                {"path": str(c_source), "sha256": subject.sha256_file(c_source)}
            ],
        }
        (self.root / "c_execution_report.json").write_text(
            json.dumps(c_execution_report), encoding="utf-8"
        )
        detailed_color = {
            "schema": "pocketworld_exact_track_truecolor_v1",
            "outputs": {"ply_sha256": hashes["ghost.ply"]},
            "color_stats": {
                "colored_points": len(ghost.xyz),
                "nonzero_rgb_points": int(np.count_nonzero(np.any(ghost.rgb != 0, axis=1))),
                "fallback_gray_points": 0,
            },
            "missing_jpeg_frames": [],
            "missing_jpeg_basenames": [],
        }
        (self.root / "detailed_color.json").write_text(json.dumps(detailed_color), encoding="utf-8")
        for layer, ply_name, zncc in (("floor", "floor.ply", 0.82), ("wall", "wall.ply", 0.83)):
            cloud = subject.read_rgb_ply(self.root / ply_name)
            source_evidence_path = self.root / f"{layer}_births.jsonl"
            source_evidence_path.write_text(
                json.dumps({"zncc_median": zncc}) + "\n", encoding="utf-8"
            )
            xyz_bits = (
                np.ascontiguousarray(cloud.xyz.astype("<f4"))
                .view("<u4")
                .reshape((-1, 3))[0]
                .astype(np.uint32)
                .tolist()
            )
            evidence = {
                "schema": "pw_b_retained_quality_evidence_v1",
                "output_sha256": hashes[ply_name],
                "point_count": 1,
                "source_birth_evidence": [
                    {
                        "path": str(source_evidence_path),
                        "sha256": subject.sha256_file(source_evidence_path),
                    }
                ],
                "rows": [
                    {
                        "output_point_index": 0,
                        "xyz_f32_bits": xyz_bits,
                        "source_file_index": 0,
                        "source_row_index": 0,
                        "zncc_median": zncc,
                        "plane_normal_output_gauge": [1.0, 0.0, 0.0],
                        "plane_value_output_gauge": float(cloud.xyz[0, 0]),
                        "abs_plane_residual_m": 0.0,
                    }
                ],
            }
            (self.root / f"{layer}_quality.json").write_text(json.dumps(evidence), encoding="utf-8")
        documents = {
            "ghost_certificate.json": {
                "schema": "pw_ghost_truecolor_certificate_v1",
                "status": "PASS",
                "output_sha256": hashes["ghost.ply"],
                "full_set_owner_arm": True,
                "generic_publish_subset": False,
                "color_source": "full_resolution_colorize",
                "gauge": "metric_replay",
                "point_count": len(ghost.xyz),
                "colorized_point_count": len(ghost.xyz),
                "nonzero_rgb_point_count": int(np.count_nonzero(np.any(ghost.rgb != 0, axis=1))),
                "source_provenance": {
                    "path": str(self.root / "detailed_color.json"),
                    "sha256": subject.sha256_file(self.root / "detailed_color.json"),
                },
            },
            "floor_certificate.json": {
                "schema": "pw_b_dense_planesweep_certificate_v1",
                "status": "PASS",
                "config": {"grid_m": 0.01, "ncc_min": 0.70},
                "forbidden_matcher_outputs_consumed": False,
                "gauge": "metric_replay",
                "output": {"sha256": hashes["floor.ply"]},
                "totals": {"accepted": 1},
                "quality": {
                    "max_abs_plane_residual_m": 0.0,
                    "zncc_median": 0.82,
                    "zncc_statistic": "actual_median_of_retained_births",
                },
                "quality_evidence": {
                    "path": str(self.root / "floor_quality.json"),
                    "sha256": subject.sha256_file(self.root / "floor_quality.json"),
                },
            },
            "wall_certificate.json": {
                "schema": "pw_b_dense_planesweep_certificate_v1",
                "status": "PASS",
                "config": {"grid_m": 0.01, "ncc_min": 0.70},
                "forbidden_matcher_outputs_consumed": False,
                "gauge": "metric_replay",
                "output": {"sha256": hashes["wall.ply"]},
                "totals": {"accepted": 1},
                "quality": {
                    "max_abs_plane_residual_m": 0.0,
                    "zncc_median": 0.83,
                    "zncc_statistic": "actual_median_of_retained_births",
                },
                "quality_evidence": {
                    "path": str(self.root / "wall_quality.json"),
                    "sha256": subject.sha256_file(self.root / "wall_quality.json"),
                },
            },
            "d_certificate.json": {
                "schema": "pw_d_final_stack_certificate_v1",
                "status": "PASS",
                "commercial_clean": True,
                "recomputed_for_final_stack": True,
                "asset_completeness": "full",
                "missing_inputs": [],
                "bindings": {
                    "ghost_gated_sparse_sha256": hashes["ghost.ply"],
                    "b_floor_sha256": [hashes["floor.ply"]],
                    "b_wall_sha256": [hashes["wall.ply"]],
                    "d_cloud_sha256": [hashes["d.ply"]],
                    "gauges": {
                        "ghost_gated_sparse": "metric_replay",
                        "b_floor": ["metric_replay"],
                        "b_wall": ["metric_replay"],
                        "d_cloud": ["metric_replay"],
                    },
                },
            },
        }
        inventory = {
            "schema": "pw_d_asset_inventory_v1",
            "capture_name": capture_name,
            "total_count": 12,
            "available_count": 12,
            "missing_inputs": [],
            "coverage_fraction": 1.0,
        }
        (self.root / "d_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
        documents["d_certificate.json"]["asset_inventory_sha256"] = subject.sha256_file(
            self.root / "d_inventory.json"
        )
        exact_d = {
            "schema": "pw_d_exact_final_input_certificate_v1",
            "status": "PASS_EXACT",
            "capture": capture_name,
            "commercial_clean": {
                "forbidden_matcher_outputs_consumed": False,
                "loftr_consumed": False,
                "scannet_consumed": False,
                "model_weights_consumed": False,
            },
            "inputs": {
                "native_library": {
                    "path": str(c_artifact),
                    "sha256": subject.sha256_file(c_artifact),
                }
            },
            "execution": {
                "final_births": 1,
                "scheduler_parity": {
                    "exact": True,
                    "floor_mask_mismatches": 0,
                    "product_birth_mask_mismatches": 0,
                    "structural_mask_mismatches": 0,
                    "wall_mask_mismatches": 0,
                },
            },
            "outputs": {
                "d_metric_gauge": {
                    "path": str(self.root / "d.ply"),
                    "sha256": hashes["d.ply"],
                    "point_count": 1,
                }
            },
        }
        (self.root / "d_exact.json").write_text(json.dumps(exact_d), encoding="utf-8")
        documents["d_certificate.json"]["exact_certificate"] = {
            "path": str(self.root / "d_exact.json"),
            "sha256": subject.sha256_file(self.root / "d_exact.json"),
        }
        documents["c_certificate.json"] = {
            "schema": "pw_c_backend_certificate_v1",
            "status": "PASS",
            "backend": "cross_platform_tiled_reference",
            "artifact": {"path": str(c_artifact), "sha256": subject.sha256_file(c_artifact)},
            "execution_report": {
                "path": str(self.root / "c_execution_report.json"),
                "sha256": subject.sha256_file(self.root / "c_execution_report.json"),
            },
        }
        for name, document in documents.items():
            (self.root / name).write_text(json.dumps(document), encoding="utf-8")
        return self._args(
            strict_final=True,
            review_classification="STRICT_FULL",
            capture_name=capture_name,
            ghost_env=[f"{key}={value}" for key, value in subject.REQUIRED_GHOST_ENV.items()],
            ghost_provenance_json=str(self.root / "ghost_certificate.json"),
            b_floor_provenance_json=[str(self.root / "floor_certificate.json")],
            b_wall_provenance_json=[str(self.root / "wall_certificate.json")],
            d_certificate_json=str(self.root / "d_certificate.json"),
            d_asset_inventory_json=str(self.root / "d_inventory.json"),
            b_floor_gauge=["metric_replay"],
            b_wall_gauge=["metric_replay"],
            d_cloud_gauge=["metric_replay"],
            c_backend=None,
            c_backend_json=str(self.root / "c_certificate.json"),
        )

    def test_full_stack_uses_gated_sparse_and_preserves_layer_order_rgb(self) -> None:
        ghost_xyz, ghost_rgb, rotation, translation = self._fixture()
        manifest = subject.assemble(self._args())
        output = subject.read_rgb_ply(self.root / "full.ply")

        expected_ghost = 2.75 * (ghost_xyz @ rotation.T) + translation
        np.testing.assert_allclose(output.xyz[:5], expected_ghost, rtol=0, atol=2e-6)
        np.testing.assert_array_equal(output.rgb[:5], ghost_rgb)
        np.testing.assert_allclose(output.xyz[5:], [[20, 21, 22], [30, 31, 32], [40, 41, 42]], atol=0)
        np.testing.assert_array_equal(output.rgb[5:], [[20, 21, 22], [30, 31, 32], [40, 41, 42]])
        self.assertEqual(manifest["output"]["point_count"], 8)
        self.assertFalse(manifest["old_device_sparse_included"])
        self.assertEqual(manifest["device_original_sparse"]["point_count"], 9)
        self.assertEqual(manifest["sim3_replay_to_device_raw"]["residual"]["inlier_count"], 11)
        self.assertLess(manifest["sim3_replay_to_device_raw"]["residual"]["rmse_inliers"], 1e-10)
        self.assertEqual(
            manifest["assembly_order"], ["ghost_gated_sparse", "b_floor[0]", "b_wall[0]", "d[0]"]
        )
        for layer in manifest["layers"]:
            self.assertEqual(layer["source_rgb_sha256"], layer["assembled_rgb_sha256"])
        self.assertEqual(
            [(item["vertex_offset_begin"], item["vertex_offset_end_exclusive"]) for item in manifest["layers"]],
            [(0, 5), (5, 6), (6, 7), (7, 8)],
        )

    def test_output_and_manifest_are_deterministic(self) -> None:
        self._fixture()
        first = subject.assemble(self._args())
        first_ply = (self.root / "full.ply").read_bytes()
        first_manifest = (self.root / "manifest.json").read_bytes()
        second = subject.assemble(self._args())
        self.assertEqual(first, second)
        self.assertEqual(first_ply, (self.root / "full.ply").read_bytes())
        self.assertEqual(first_manifest, (self.root / "manifest.json").read_bytes())

    def test_required_missing_layer_fails_closed_and_records_it(self) -> None:
        self._fixture()
        args = self._args(b_wall=[])
        with self.assertRaises(subject.AssemblyError):
            subject.assemble(args)
        manifest = json.loads((self.root / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "input_error")
        self.assertEqual(manifest["required_layers_not_declared"], ["b_wall"])
        self.assertFalse((self.root / "full.ply").exists())

    def test_rgb_reader_supports_binary_with_extra_scalar_properties(self) -> None:
        xyz = np.asarray([[1.25, 2.5, -3.75], [4.0, 5.0, 6.0]])
        rgb = np.asarray([[250, 2, 3], [4, 5, 6]], dtype=np.uint8)
        base = subject.Cloud(xyz, rgb)
        path = self.root / "binary.ply"
        subject.write_rgb_ply(path, [base])
        loaded = subject.read_rgb_ply(path)
        np.testing.assert_allclose(loaded.xyz, xyz, atol=0)
        np.testing.assert_array_equal(loaded.rgb, rgb)

    def test_strict_final_binds_truecolour_dense_b_and_recomputed_d(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        manifest = subject.assemble(args)
        self.assertTrue(manifest["strict_final"])
        self.assertIn("d_final_stack_certificate", manifest["provenance"])
        for layer in manifest["layers"]:
            self.assertTrue(layer["sim3_replay_to_device_raw_applied"])

    def test_strict_final_rejects_coarse_b_and_stale_d_binding(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        certificate = json.loads((self.root / "floor_certificate.json").read_text())
        certificate["config"]["grid_m"] = 0.05
        (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "actual <=1cm resweep"):
            subject.assemble(args)

        args = self._valid_strict_args()
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["bindings"]["ghost_gated_sparse_sha256"] = "0" * 64
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "structured input bindings"):
            subject.assemble(args)

    def test_strict_final_rejects_wrong_env_missing_layer_and_unverified_c(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        args.ghost_env[-1] = "AETHER_EXACT_SITE_OWNER_MIN_DEPTH_M=0.011"
        with self.assertRaisesRegex(subject.AssemblyError, "exact ghost environment"):
            subject.assemble(args)

        args = self._valid_strict_args()
        args.b_wall = []
        args.b_wall_provenance_json = []
        with self.assertRaisesRegex(subject.AssemblyError, "required layers absent"):
            subject.assemble(args)

        args = self._valid_strict_args()
        args.c_backend = "unverified-literal"
        args.c_backend_json = None
        with self.assertRaisesRegex(subject.AssemblyError, "c_backend_verified_json_only"):
            subject.assemble(args)

        args = self._valid_strict_args()
        (self.root / "libaether_test.dylib").write_bytes(b"tampered")
        with self.assertRaisesRegex(subject.AssemblyError, "C artifact SHA mismatch"):
            subject.assemble(args)

    def test_strict_final_rejects_forged_or_unexercised_c_report(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        certificate = json.loads((self.root / "c_certificate.json").read_text())
        certificate.pop("execution_report")
        (self.root / "c_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "execution report binding missing"):
            subject.assemble(args)

        args = self._valid_strict_args()
        report = json.loads((self.root / "c_execution_report.json").read_text())
        report["backend_exercised"] = False
        (self.root / "c_execution_report.json").write_text(json.dumps(report), encoding="utf-8")
        certificate = json.loads((self.root / "c_certificate.json").read_text())
        certificate["execution_report"]["sha256"] = subject.sha256_file(
            self.root / "c_execution_report.json"
        )
        (self.root / "c_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "not actually exercised"):
            subject.assemble(args)

        args = self._valid_strict_args()
        report = json.loads((self.root / "c_execution_report.json").read_text())
        report["executions"][0]["output_validation"]["mismatch_count"] = 1
        (self.root / "c_execution_report.json").write_text(json.dumps(report), encoding="utf-8")
        certificate = json.loads((self.root / "c_certificate.json").read_text())
        certificate["execution_report"]["sha256"] = subject.sha256_file(
            self.root / "c_execution_report.json"
        )
        (self.root / "c_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "not bit-exact"):
            subject.assemble(args)

    def test_strict_final_rejects_b_evidence_not_bound_to_output_xyz(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        evidence = json.loads((self.root / "floor_quality.json").read_text())
        evidence["rows"][0]["xyz_f32_bits"][0] ^= 1
        (self.root / "floor_quality.json").write_text(json.dumps(evidence), encoding="utf-8")
        certificate = json.loads((self.root / "floor_certificate.json").read_text())
        certificate["quality_evidence"]["sha256"] = subject.sha256_file(
            self.root / "floor_quality.json"
        )
        (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "XYZ/order is not bit-exact"):
            subject.assemble(args)

        args = self._valid_strict_args()
        evidence = json.loads((self.root / "floor_quality.json").read_text())
        evidence["rows"][0]["plane_value_output_gauge"] = 21.0
        evidence["rows"][0]["abs_plane_residual_m"] = 0.0
        (self.root / "floor_quality.json").write_text(json.dumps(evidence), encoding="utf-8")
        certificate = json.loads((self.root / "floor_certificate.json").read_text())
        certificate["quality_evidence"]["sha256"] = subject.sha256_file(
            self.root / "floor_quality.json"
        )
        (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "plane residual does not match output XYZ"):
            subject.assemble(args)

    def test_strict_final_rejects_d_exact_execution_mismatch(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        exact = json.loads((self.root / "d_exact.json").read_text())
        exact["execution"]["final_births"] = 2
        (self.root / "d_exact.json").write_text(json.dumps(exact), encoding="utf-8")
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["exact_certificate"]["sha256"] = subject.sha256_file(
            self.root / "d_exact.json"
        )
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "birth count does not match"):
            subject.assemble(args)

        args = self._valid_strict_args()
        exact = json.loads((self.root / "d_exact.json").read_text())
        exact["execution"]["scheduler_parity"]["wall_mask_mismatches"] = 1
        (self.root / "d_exact.json").write_text(json.dumps(exact), encoding="utf-8")
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["exact_certificate"]["sha256"] = subject.sha256_file(
            self.root / "d_exact.json"
        )
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "zero-mismatch"):
            subject.assemble(args)

    def test_strict_final_rejects_unqualified_d_certificate(self) -> None:
        self._fixture()
        for mutation, pattern in (
            (("status", "FAIL"), "schema/status"),
            (("commercial_clean", False), "commercial-clean"),
            (("recomputed_for_final_stack", False), "commercial-clean"),
            (("asset_completeness", "unknown"), "asset_completeness"),
        ):
            with self.subTest(mutation=mutation):
                args = self._valid_strict_args()
                certificate = json.loads((self.root / "d_certificate.json").read_text())
                certificate[mutation[0]] = mutation[1]
                (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
                with self.assertRaisesRegex(subject.AssemblyError, pattern):
                    subject.assemble(args)

        args = self._valid_strict_args()
        certificate = json.loads((self.root / "floor_certificate.json").read_text())
        certificate["quality"]["zncc_median"] = 0.70
        certificate["quality"]["zncc_semantics"] = "configured certified lower_bound"
        (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "lower bound"):
            subject.assemble(args)

        args = self._valid_strict_args()
        certificate = json.loads((self.root / "floor_certificate.json").read_text())
        certificate["quality"]["zncc_median"] = 0.80
        (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "does not match retained evidence"):
            subject.assemble(args)

        args = self._valid_strict_args()
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["asset_completeness"] = "partial"
        certificate["missing_inputs"] = ["frame_7.jpg"]
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "historical partial D"):
            subject.assemble(args)

    def test_strict_final_accepts_explicit_consistent_cap50_partial_inventory(self) -> None:
        self._fixture()
        args = self._valid_strict_args("cap50")
        inventory = {
            "schema": "pw_d_asset_inventory_v1",
            "capture_name": "cap50",
            "total_count": 12,
            "available_count": 10,
            "missing_inputs": [
                {"id": "frame_7", "path": "photos_highres/frame_7.jpg"},
                {"id": "frame_9", "path": "photos_highres/frame_9.jpg"},
            ],
            "coverage_fraction": 10 / 12,
        }
        (self.root / "d_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["asset_completeness"] = "partial"
        certificate["asset_inventory_sha256"] = subject.sha256_file(self.root / "d_inventory.json")
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        manifest = subject.assemble(args)
        d_provenance = manifest["provenance"]["d_final_stack_certificate"]
        self.assertEqual(d_provenance["asset_completeness"], "partial")
        self.assertEqual(d_provenance["asset_available_count"], 10)
        self.assertEqual(len(d_provenance["missing_inputs"]), 2)

        args = self._valid_strict_args("cap50")
        (self.root / "d_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
        certificate = json.loads((self.root / "d_certificate.json").read_text())
        certificate["asset_inventory_sha256"] = subject.sha256_file(self.root / "d_inventory.json")
        (self.root / "d_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "claims full assets"):
            subject.assemble(args)

    def test_metric_layers_share_sim3_and_wrong_gauge_is_rejected(self) -> None:
        _, _, rotation, translation = self._fixture()
        args = self._valid_strict_args()
        manifest = subject.assemble(args)
        output = subject.read_rgb_ply(self.root / "full.ply")
        floor_offset = manifest["layers"][1]["vertex_offset_begin"]
        expected_floor = 2.75 * (np.asarray([[20.0, 21.0, 22.0]]) @ rotation.T) + translation
        np.testing.assert_allclose(output.xyz[floor_offset : floor_offset + 1], expected_floor, atol=1e-5)
        self.assertTrue(manifest["layers"][1]["sim3_replay_to_device_raw_applied"])

        args = self._valid_strict_args()
        args.b_floor_gauge = ["device_raw"]
        with self.assertRaisesRegex(subject.AssemblyError, "provenance gauge"):
            subject.assemble(args)

    def test_cap41_saved_b_is_metric_scale_not_device_raw_scale(self) -> None:
        device_path = Path("/tmp/pw_device_exact_evidence_20260716/cap41/sfm_sparse.ply")
        b_path = Path(
            __file__
        ).resolve().parents[1] / "cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/floor_reference_sweep/structural_planesweep_main.ply"
        if not device_path.is_file() or not b_path.is_file():
            self.skipTest("cap41 immutable gauge fixtures are not present")
        device = subject.read_rgb_ply(device_path)
        b_cloud = subject.read_rgb_ply(b_path)
        device_diagonal = subject._bbox_stats(device)["diagonal"]
        b_diagonal = subject._bbox_stats(b_cloud)["diagonal"]
        self.assertLess(b_diagonal / device_diagonal, 0.03)
        self.assertGreater(device_diagonal, 100.0)
        self.assertLess(b_diagonal, 5.0)

        device_centres, _, _ = subject.read_device_centres(
            Path("/tmp/pw_device_exact_evidence_20260716/cap41/sfm_sparse_meta.json"), "tvec"
        )
        replay_centres, _, _, _, _ = subject.read_replay_centres(
            Path("/tmp/pw_full_stack_20260716/cap41/ghost_owner_full/solved_poses.csv"), "tvec"
        )
        frame_ids = sorted(set(device_centres) & set(replay_centres), key=lambda value: (len(value), value))
        transform, _, residual = subject.robust_sim3(
            np.vstack([replay_centres[value] for value in frame_ids]),
            np.vstack([device_centres[value] for value in frame_ids]),
        )
        self.assertGreater(residual["p95_inliers"], subject.STRICT_MAX_SIM3_P95_M)
        self.assertLess(
            residual["p95_inliers"] / transform.scale,
            subject.STRICT_MAX_SIM3_P95_M,
        )

        replay_to_metric = Path(
            __file__
        ).resolve().parent / "runs/d_final/cap41/metric_transform_manifest.json"
        metric_to_raw = Path(
            __file__
        ).resolve().parent / "runs/d_final/cap41/raw_transform_manifest.json"
        ghost_path = Path("/tmp/pw_full_stack_20260716/colorized/cap41_ghost_owner_full_truecolor.ply")
        if replay_to_metric.is_file() and metric_to_raw.is_file() and ghost_path.is_file():
            ghost = subject.read_rgb_ply(ghost_path)
            chained, evidence, chained_residual = subject.load_certified_chained_sim3(
                replay_to_metric, metric_to_raw, ghost_path, ghost
            )
            self.assertEqual(evidence["kind"], "certified_replay_metric_raw_chain")
            self.assertGreater(chained.scale, 20.0)
            self.assertLess(chained_residual["p95_inliers"], 1e-4)

            raw_anchor_path = replay_to_metric.parent / "ghost_owner_full_device_raw_gauge.ply"
            if raw_anchor_path.is_file():
                baseline_stats = subject._device_baseline_alignment_stats(
                    device, subject.read_rgb_ply(raw_anchor_path), chained.scale
                )
                self.assertGreater(
                    baseline_stats["candidate_to_device_diagonal_ratio"],
                    subject.STRICT_BASELINE_DIAGONAL_RATIO_MAX,
                )
                self.assertLess(
                    baseline_stats["candidate_to_device"]["within_3cm_fraction"],
                    subject.STRICT_BASELINE_MIN_WITHIN_3CM_FRACTION,
                )
                with self.assertRaisesRegex(subject.AssemblyError, "device baseline geometry mismatch"):
                    subject._validate_device_baseline_alignment(baseline_stats)

    def test_saved_cap41_visual_candidate_is_explicitly_rejected(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parent
            / "runs/research_candidate/cap41/research_candidate_manifest.json"
        )
        if not manifest_path.is_file():
            self.skipTest("saved cap41 visual candidate is not present")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "rejected_geometry_mismatch")
        self.assertEqual(manifest["review_classification"], "REJECTED_GEOMETRY_MISMATCH")
        alignment = manifest["device_baseline_geometry_alignment"]
        self.assertEqual(alignment["status"], "REJECTED_GEOMETRY_MISMATCH")
        self.assertGreater(
            alignment["candidate_to_device_diagonal_ratio"],
            subject.STRICT_BASELINE_DIAGONAL_RATIO_MAX,
        )

    def test_strict_final_rejects_cloud_that_matches_poses_but_not_device_geometry(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        device = subject.read_rgb_ply(self.root / "device.ply")
        write_ascii_ply(self.root / "device.ply", device.xyz + 100.0, device.rgb)
        with self.assertRaisesRegex(subject.AssemblyError, "device baseline geometry mismatch"):
            subject.assemble(args)
        rejection = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(rejection["status"], "rejected_device_baseline_geometry")
        self.assertEqual(
            rejection["device_baseline_geometry_alignment"]["status"],
            "REJECTED_GEOMETRY_MISMATCH",
        )
        self.assertFalse((self.root / "full.ply").exists())

    def test_strict_final_rejects_non100_registration_and_bad_sim3(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        args.expected_registered = 11
        with self.assertRaisesRegex(subject.AssemblyError, "registered frame mismatch"):
            subject.assemble(args)

        self._fixture()
        args = self._valid_strict_args()
        device = json.loads((self.root / "device.json").read_text())
        for index in (1, 2, 3, 4):
            device["poses"][index]["t"][0] += 100.0 + index
        (self.root / "device.json").write_text(json.dumps(device), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "Sim3 inlier fraction"):
            subject.assemble(args)

    def test_strict_final_rejects_low_rgb_coverage_and_bad_b_quality(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        ghost = subject.read_rgb_ply(self.root / "ghost.ply")
        low_rgb = ghost.rgb.copy()
        low_rgb[:4] = 0
        write_ascii_ply(self.root / "ghost.ply", ghost.xyz, low_rgb)
        ghost_hash = subject.sha256_file(self.root / "ghost.ply")
        certificate = json.loads((self.root / "ghost_certificate.json").read_text())
        certificate["output_sha256"] = ghost_hash
        certificate["nonzero_rgb_point_count"] = 1
        detailed = json.loads((self.root / "detailed_color.json").read_text())
        detailed["outputs"]["ply_sha256"] = ghost_hash
        detailed["color_stats"]["nonzero_rgb_points"] = 1
        (self.root / "detailed_color.json").write_text(json.dumps(detailed), encoding="utf-8")
        certificate["source_provenance"]["sha256"] = subject.sha256_file(
            self.root / "detailed_color.json"
        )
        (self.root / "ghost_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssemblyError, "true-colour nonzero coverage"):
            subject.assemble(args)

        for mutation, pattern in (
            (("status", "FAIL"), "schema/status"),
            (("accepted", 0), "accepted count"),
            (("offplane", 0.01), "off-plane residual"),
            (("zncc", 0.2), "ZNCC quality"),
        ):
            with self.subTest(mutation=mutation):
                self._fixture()
                args = self._valid_strict_args()
                certificate = json.loads((self.root / "floor_certificate.json").read_text())
                key, value = mutation
                if key == "status":
                    certificate["status"] = value
                elif key == "accepted":
                    certificate["totals"]["accepted"] = value
                elif key == "offplane":
                    certificate["quality"]["max_abs_plane_residual_m"] = value
                else:
                    certificate["quality"]["zncc_median"] = value
                (self.root / "floor_certificate.json").write_text(json.dumps(certificate), encoding="utf-8")
                with self.assertRaisesRegex(subject.AssemblyError, pattern):
                    subject.assemble(args)

    def test_cap40_requires_explicit_historical_registration_exception(self) -> None:
        self._fixture()
        with (self.root / "poses.csv").open() as stream:
            rows = list(csv.reader(stream))
        rows = rows[:-4]
        with (self.root / "poses.csv").open("w", newline="") as stream:
            csv.writer(stream).writerows(rows)
        ledger_ids = [*range(8), 79, 80, 81, 82]
        (self.root / "ledger.jsonl").write_text(
            "".join(json.dumps({"frameId": value}) + "\n" for value in ledger_ids),
            encoding="utf-8",
        )
        args = self._valid_strict_args("cap40")
        args.expected_registered = 8
        args.expected_frame_count = 12
        exception = {
            "schema": "pw_cap40_registration_exception_v1",
            "status": "HISTORICAL_INPUT_EXCEPTION",
            "capture_name": "cap40",
            "replay_registered": 8,
            "replay_pose_rows": 8,
            "ledger_frame_count": 12,
            "unregistered_frame_ids": ["79", "80", "81", "82"],
        }
        path = self.root / "registration_exception.json"
        path.write_text(json.dumps(exception), encoding="utf-8")
        args.registration_exception_json = str(path)
        manifest = subject.assemble(args)
        self.assertEqual(
            manifest["registration"]["verdict"]["status"], "HISTORICAL_INPUT_EXCEPTION"
        )

    def test_strict_registration_is_derived_from_immutable_ledger(self) -> None:
        self._fixture()
        args = self._valid_strict_args()
        with (self.root / "poses.csv").open() as stream:
            rows = list(csv.reader(stream))
        with (self.root / "poses.csv").open("w", newline="") as stream:
            csv.writer(stream).writerows(rows[:-1])
        args.expected_registered = 11
        with self.assertRaisesRegex(subject.AssemblyError, "pose IDs exactly equal immutable ledger"):
            subject.assemble(args)

        self._fixture()
        args = self._valid_strict_args()
        with (self.root / "poses.csv").open() as stream:
            rows = list(csv.reader(stream))
        rows[-1][0] = "999"
        with (self.root / "poses.csv").open("w", newline="") as stream:
            csv.writer(stream).writerows(rows)
        with self.assertRaisesRegex(subject.AssemblyError, "absent from immutable replay ledger"):
            subject.assemble(args)

        self._fixture()
        args = self._valid_strict_args()
        with (self.root / "ledger.jsonl").open("a") as stream:
            stream.write(json.dumps({"frameId": 3}) + "\n")
        with self.assertRaisesRegex(subject.AssemblyError, "duplicate frameId 3"):
            subject.assemble(args)

        self._fixture()
        args = self._valid_strict_args()
        ledger = [*range(11), 99]
        (self.root / "ledger.jsonl").write_text(
            "".join(json.dumps({"frameId": value}) + "\n" for value in ledger),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(subject.AssemblyError, "absent from immutable replay ledger"):
            subject.assemble(args)


if __name__ == "__main__":
    unittest.main()
