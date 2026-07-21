from __future__ import annotations

import importlib
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
if str(PYTHON_TOOLS) not in sys.path:
    sys.path.insert(0, str(PYTHON_TOOLS))


STRICT_GATES = {
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _list_hash(names):
    return hashlib.sha256(("\n".join(names) + "\n").encode()).hexdigest()


def _write_binding_fixture(
    root: Path,
    fixture,
    *,
    dataset_id="fixture_quality",
    split_id="fixture_1r1h_strict",
    coordinate_frame="optimized_sfm_cv",
    metres_per_model_unit=1.007804831494465,
):
    import b0_input_contract
    import mesh_ab_eval

    archive = root / "frames.npz"
    np.savez(archive, **fixture)
    evaluation_digest = mesh_ab_eval.frozen_input_digest(fixture)
    reconstruction = ["r0.jpg"]
    heldout = fixture["frames"].tolist()
    reconstruction_hash = _list_hash(reconstruction)
    heldout_hash = _list_hash(heldout)
    reconstruction_semantic = b0_input_contract.ordered_frame_names_sha256(
        reconstruction
    )
    heldout_ordered_semantic = b0_input_contract.ordered_frame_names_sha256(
        heldout
    )
    route_digest = "a" * 64
    heldout_semantic = b0_input_contract.semantic_manifest_sha256(
        b0_input_contract.canonical_frame_semantic_sha256(
            name,
            np.isfinite(fixture["depth"][index]) & (fixture["depth"][index] > 0),
            fixture["depth"][index],
            fixture["K"][index],
            fixture["w2c"][index],
        )
        for index, name in enumerate(heldout)
    )
    universe = reconstruction + heldout
    by_name = {
        name: {
            "sha256": hashlib.sha256(name.encode()).hexdigest(),
            "size_bytes": 1,
        }
        for name in universe
    }
    image_manifest = b0_input_contract.image_identity_manifest_sha256(
        universe, by_name
    )
    transductive_policy = {
        "present": True,
        "route_allowed": True,
        "quality_scoring_forbidden": False,
        "warning": "fixture transductive observation-consistency only",
    }
    input_payload = {
        "schema_version": "b0-input-contract-v1",
        "dataset_id": dataset_id,
        "coordinate_frame": coordinate_frame,
        "metres_per_model_unit": metres_per_model_unit,
        "transductive_policy": transductive_policy,
        "dmcache": {
            "sha256": "1" * 64,
            "signature": "fixture-camera-z",
            "depth": {"shape": [len(universe), 3, 3], "dtype": "float32"},
            "frame_order": universe,
            "frame_order_sha256": b0_input_contract.ordered_frame_names_sha256(
                universe
            ),
        },
        "model_cache": {
            "sha256": "2" * 64,
            "frame_order": universe,
            "frame_order_sha256": b0_input_contract.ordered_frame_names_sha256(
                universe
            ),
        },
        "splits": {
            split_id: {
                "dataset_id": dataset_id,
                "route_allowed": True,
                "quality_scoring_forbidden": False,
                "reconstruction": {
                    "frames": reconstruction,
                    "file_sha256": reconstruction_hash,
                    "semantic_sha256": reconstruction_semantic,
                },
                "heldout": {
                    "frames": heldout,
                    "file_sha256": heldout_hash,
                    "semantic_sha256": heldout_ordered_semantic,
                },
            }
        },
        "images": {"root_manifest_sha256": image_manifest, "by_name": by_name},
    }
    input_contract_path = root / "input_contract.json"
    input_contract_path.write_text(json.dumps(input_payload))
    input_contract_sha256 = _sha256(input_contract_path)
    source_bundle_sha256 = "3" * 64
    alicevision_binary_path = "/opt/pocketworld/aliceVision_meshing"
    alicevision_binary_sha256 = "4" * 64
    environment_sha256 = "5" * 64
    formal_children = {
        "tsdf_meshing": [sys.executable, "fixture-tsdf-meshing"],
        "fusecut_meshing": [
            alicevision_binary_path,
            "--outputMesh",
            str(root / "fusecut" / "mesh.obj"),
        ],
    }
    contract = {
        "schema_version": "b0-preregistration-v1",
        "only_experimental_variable": "meshing_backend",
        "dataset_id": dataset_id,
        "input_split_id": split_id,
        "frozen_authority": {
            "source_state": {
                "dirty_code_bundle": {"bundle_sha256": source_bundle_sha256}
            },
            "alicevision_binary": {
                "path": alicevision_binary_path,
                "sha256": alicevision_binary_sha256,
            },
            "environment_identity": {"sha256": environment_sha256},
            "input_contract": {
                "schema_version": "b0-input-contract-v1",
                "raw_sha256": input_contract_sha256,
                "dataset_id": dataset_id,
                "split_id": split_id,
                "coordinate_frame": coordinate_frame,
                "metres_per_model_unit": metres_per_model_unit,
                "universe_count": len(universe),
                "reconstruction_count": len(reconstruction),
                "heldout_count": len(heldout),
            },
            "data_sha256": {
                "dmcache": "1" * 64,
                "model_cache": "2" * 64,
                "images_root_manifest": image_manifest,
            }
        },
        "splits": {
            dataset_id: {
                "source_input_contract_split_id": split_id,
                "universe_count": len(universe),
                "reconstruction_count": len(reconstruction),
                "heldout_count": len(heldout),
                "quality_claim_allowed": True,
                "list_sha256": {
                    "reconstruction": reconstruction_hash,
                    "heldout": heldout_hash,
                },
            }
        },
        "execution_plan": {
            dataset_id: {
                "input_contract_split_id": split_id,
                "quality_scoring_forbidden": False,
            },
            "formal_runner_bindings": {
                phase: {
                    "child_argv": argv,
                    "child_argv_sha256": hashlib.sha256(
                        json.dumps(
                            argv,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                }
                for phase, argv in formal_children.items()
            },
        },
        "gates": {"b0_prompt_strict": STRICT_GATES},
        "improvement_claim": {
            "bootstrap_draws": 10_000,
            "seed": 20260721,
            "confidence_interval": "two-sided percentile 95%; use lower bound",
            "required_low_texture_coverage_lower_bound": 0.05,
            "required_weak_support_coverage_lower_bound": 0.05,
            "also_requires_all_noninferiority_gates": True,
            "unit": "paired held-out frame",
        },
    }
    contract_path = root / "contract.json"
    contract_path.write_text(json.dumps(contract))
    prepared = {
        "schema_version": "b0-prepared-evaluation-provenance-v1",
        "artifact_schema_version": "b0-prepared-evaluation-v1",
        "input_only": True,
        "mesh_inputs_accepted": False,
        "dataset_id": dataset_id,
        "split_id": split_id,
        "split_profile": split_id,
        "route_allowed": True,
        "quality_scoring_forbidden": False,
        "split_binding": {
            "dataset_id": dataset_id,
            "split_id": split_id,
            "route_allowed": True,
            "quality_scoring_forbidden": False,
            "reconstruction_file_sha256": reconstruction_hash,
            "heldout_file_sha256": heldout_hash,
            "reconstruction_ordered_semantic_sha256": reconstruction_semantic,
            "heldout_ordered_semantic_sha256": heldout_ordered_semantic,
        },
        "frame_order": heldout,
        "frame_count": len(heldout),
        "shape": list(fixture["depth"].shape),
        "component_sha256": {
            "output_npz": _sha256(archive),
            "reconstruction_list": reconstruction_hash,
            "heldout_list": heldout_hash,
            "dmcache": "1" * 64,
            "model_cache": "2" * 64,
            "input_contract": input_contract_sha256,
            "registered_image_root_manifest": image_manifest,
            "mesh_ab_eval.py": _sha256(PYTHON_TOOLS / "mesh_ab_eval.py"),
            "b0_prepare_eval.py": _sha256(PYTHON_TOOLS / "b0_prepare_eval.py"),
        },
        "semantic_manifest_sha256": {
            "reconstruction": route_digest,
            "heldout": heldout_semantic,
        },
        "coordinate_scale": {
            "stored_coordinate_frame": coordinate_frame,
            "contract_coordinate_frame": coordinate_frame,
            "stored_arrays_rescaled": False,
            "metres_per_model_unit": metres_per_model_unit,
            "absolute_threshold_conversion": (
                "model_units = metres / metres_per_model_unit"
            ),
        },
        "evaluator_digest": evaluation_digest,
        "evaluation_digest": evaluation_digest,
    }
    prepared_path = root / "frames.npz.provenance.json"
    prepared_path.write_text(json.dumps(prepared))
    route = {
        "schema": "pocketworld.b0.tsdf.provenance.v2",
        "dataset_id": dataset_id,
        "split_id": split_id,
        "coordinate_frame": coordinate_frame,
        "metres_per_model_unit": metres_per_model_unit,
        "transductive_policy": transductive_policy,
        "frame_count": len(reconstruction),
        "frame_order": reconstruction,
        "frame_list_sha256": reconstruction_hash,
        "semantic_manifest_sha256": route_digest,
        "dmcache_sha256": "1" * 64,
        "model_cache_sha256": "2" * 64,
        "frozen_input_identity_contract": {
            "path": str(input_contract_path),
            "sha256": input_contract_sha256,
            "schema_version": "b0-input-contract-v1",
            "split_id": split_id,
            "validated_fields": {
                "dataset_id": dataset_id,
                "coordinate_frame": coordinate_frame,
                "metres_per_model_unit": metres_per_model_unit,
                "transductive_policy": transductive_policy,
                "dmcache_frame_order_sha256": input_payload["dmcache"][
                    "frame_order_sha256"
                ],
                "model_cache_frame_order_sha256": input_payload["model_cache"][
                    "frame_order_sha256"
                ],
                "reconstruction_file_sha256": reconstruction_hash,
                "reconstruction_semantic_sha256": reconstruction_semantic,
                "heldout_file_sha256": heldout_hash,
                "heldout_semantic_sha256": heldout_ordered_semantic,
                "image_root_manifest_sha256": image_manifest,
            },
        },
        "coordinate_transform": {
            "mesh_output": coordinate_frame,
            "metres_per_model_unit": metres_per_model_unit,
            "transform_applied_by_route": False,
            "sim3_applied_to_mesh": False,
            "icp_applied_to_mesh": False,
        },
    }
    route_path = root / "route.json"
    route_path.write_text(json.dumps(route))
    return archive, prepared_path, contract_path, route_path, input_contract_path


def _bind_tsdf_route_mesh(route_path: Path, mesh_path: Path) -> None:
    payload = json.loads(route_path.read_text())
    payload["mesh"] = {
        **payload.get("mesh", {}),
        "path": mesh_path.name,
        "bytes": mesh_path.stat().st_size,
        "sha256": _sha256(mesh_path),
    }
    route_path.write_text(json.dumps(payload))


def _write_monitor_status(
    root: Path,
    *,
    contract_path: Path,
    mesh_path: Path,
    phase: str,
    name: str,
) -> Path:
    contract = json.loads(contract_path.read_text())
    authority = contract["frozen_authority"]
    phase_binding = contract["execution_plan"]["formal_runner_bindings"][phase]
    status_path = (root / name / "status.json").resolve()
    status_path.parent.mkdir(parents=True)
    status = {
        "schema_version": "b0-monitored-command-v1",
        "label": phase,
        "verdict": "PASS",
        "command_outcome": "SUCCESS",
        "started": True,
        "exit_code": 0,
        "launch_error": None,
        "command": {
            "argv": phase_binding["child_argv"],
            "shell": False,
            "canonical_sha256": phase_binding["child_argv_sha256"],
        },
        "formal_binding": {
            "status": "VERIFIED",
            "contract_path": str(contract_path.resolve()),
            "contract_sha256": _sha256(contract_path),
            "contract_sidecar_path": str(contract_path.with_suffix(".sha256")),
            "phase": phase,
            "child_argv_sha256": phase_binding["child_argv_sha256"],
            "source_bundle_sha256": authority["source_state"][
                "dirty_code_bundle"
            ]["bundle_sha256"],
            "alicevision_binary_sha256": authority["alicevision_binary"]["sha256"],
            "environment_sha256": authority["environment_identity"]["sha256"],
        },
        "environment": {
            "allowlist": [],
            "effective": {},
            "canonical_sha256": hashlib.sha256(b"{}").hexdigest(),
        },
        "attestation": {
            "status": "VERIFIED",
            "files": [
                {
                    "path": str(mesh_path.resolve()),
                    "size_bytes": mesh_path.stat().st_size,
                    "sha256": _sha256(mesh_path),
                }
            ],
            "trees": [],
            "errors": [],
        },
    }
    status_path.write_text(json.dumps(status))
    return status_path


class LazyImportTests(unittest.TestCase):
    def test_import_does_not_import_open3d(self):
        sys.modules.pop("pw_mesh_bench", None)
        sys.modules.pop("open3d", None)
        importlib.import_module("pw_mesh_bench")
        self.assertNotIn("open3d", sys.modules)

    def test_nonplanar_fixture_does_not_touch_or_expand_per_ray_intersections(self):
        import pw_mesh_bench

        class Untouchable:
            def __getitem__(self, _key):
                raise AssertionError("non-planar multi-hit payload was touched")

        sparse = pw_mesh_bench._fixture_sparse_intersections(
            Untouchable(),
            Untouchable(),
            frame_index=0,
            ray_count=2_000_000,
            selected_ids=np.empty(0, dtype=np.int64),
        )
        self.assertEqual(sparse, {})

    def test_large_multihit_grouping_uses_one_sorted_pass_and_bounded_array_payload(self):
        import pw_mesh_bench

        ray_count = 25_000
        hits_per_ray = 4
        ray_ids = np.repeat(np.arange(ray_count, dtype=np.int64), hits_per_ray)
        depth = np.tile(np.array([2.0, 2.01, 2.02, 2.03]), ray_count)
        normals = np.tile(np.array([[0.0, 0.0, -1.0]]), (len(ray_ids), 1))
        order = np.random.default_rng(20260721).permutation(len(ray_ids))
        with mock.patch.object(
            pw_mesh_bench.np,
            "unique",
            side_effect=AssertionError("per-ray equality-mask grouping regressed"),
        ):
            grouped = pw_mesh_bench._group_listed_intersections(
                local_ray_ids=ray_ids[order],
                listed_z=depth[order],
                listed_normals_camera=normals[order],
                selected_ids=np.arange(ray_count, dtype=np.int64),
            )
        self.assertEqual(len(grouped), ray_count)
        np.testing.assert_allclose(
            grouped[12_345][0], [2.0, 2.01, 2.02, 2.03], rtol=0, atol=1e-6
        )
        payload_bytes = sum(z.nbytes + n.nbytes for z, n in grouped.values())
        self.assertLessEqual(payload_bytes, depth.nbytes + normals.nbytes)


class ProductionRaycastRegressionTests(unittest.TestCase):
    @staticmethod
    def _arrays():
        return {
            "frames": np.array(["f0.jpg"]),
            "depth": np.array([[[2.0]]], np.float32),
            "K": np.array([[[1.0, 0.0, -0.1], [0.0, 1.0, -0.2], [0.0, 0.0, 1.0]]]),
            "w2c": np.eye(4, dtype=np.float64)[None],
            "roi": np.ones((1, 1, 1), bool),
            "low_texture": np.ones((1, 1, 1), bool),
            "weak_support": np.ones((1, 1, 1), bool),
            "planar_single_surface": np.ones((1, 1, 1), bool),
        }

    def test_closed_thin_box_is_not_a_double_shell_in_production_raycast(self):
        try:
            import open3d as o3d
        except ImportError:
            self.skipTest("Open3D unavailable")
        import mesh_ab_eval
        import pw_mesh_bench

        mesh = o3d.geometry.TriangleMesh.create_box(width=2.0, height=2.0, depth=0.02)
        mesh.translate((-1.0, -1.0, 2.0))
        arrays = self._arrays()
        frame_index, _, _, sparse = next(pw_mesh_bench._raycast_mesh(
            arrays, np.asarray(mesh.vertices), np.asarray(mesh.triangles)
        ))
        self.assertEqual(frame_index, 0)
        result = mesh_ab_eval.double_shell_metrics(
            observed_z=arrays["depth"][0].reshape(-1),
            eligible_mask=np.array([True]),
            sparse_intersections=sparse,
            metres_per_model_unit=1.0,
        )
        self.assertEqual(result["event_count"], 0)

    def test_two_same_winding_open_surfaces_are_a_double_shell_in_production_raycast(self):
        try:
            import open3d  # noqa: F401
        except ImportError:
            self.skipTest("Open3D unavailable")
        import mesh_ab_eval
        import pw_mesh_bench

        vertices = []
        faces = []
        for z in (2.0, 2.02):
            offset = len(vertices)
            vertices.extend([[-1, -1, z], [1, -1, z], [1, 1, z], [-1, 1, z]])
            # Both planes face the camera (-Z); their signed normals agree.
            faces.extend([[offset, offset + 2, offset + 1], [offset, offset + 3, offset + 2]])
        arrays = self._arrays()
        frame_index, _, _, sparse = next(pw_mesh_bench._raycast_mesh(
            arrays, np.asarray(vertices, float), np.asarray(faces, np.int64)
        ))
        self.assertEqual(frame_index, 0)
        result = mesh_ab_eval.double_shell_metrics(
            observed_z=arrays["depth"][0].reshape(-1),
            eligible_mask=np.array([True]),
            sparse_intersections=sparse,
            metres_per_model_unit=1.0,
        )
        self.assertEqual(result["event_count"], 1)


class ProvenanceBindingTests(unittest.TestCase):
    def fixture(self):
        return {
            "frames": np.array(["f0.jpg"]),
            "depth": np.full((1, 3, 3), 2.0, np.float32),
            "K": np.eye(3, dtype=np.float64)[None],
            "w2c": np.eye(4, dtype=np.float64)[None],
            "roi": np.ones((1, 3, 3), bool),
            "low_texture": np.ones((1, 3, 3), bool),
            "weak_support": np.ones((1, 3, 3), bool),
            "planar_single_surface": np.ones((1, 3, 3), bool),
        }

    def test_binding_covers_split_archive_evaluator_and_route_semantics(self):
        import pw_mesh_bench

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            arrays = pw_mesh_bench._load_contract_archive(archive)
            binding, _, _ = pw_mesh_bench._validate_experiment_binding(
                arrays=arrays,
                frames_path=archive,
                prepared_provenance_path=prepared,
                preregistered_contract_path=contract,
                input_contract_path=input_contract,
                split_id="fixture_1r1h_strict",
                route_provenance_path=route,
            )
            self.assertEqual(binding["dataset_id"], "fixture_quality")
            self.assertEqual(binding["coordinate_frame"], "optimized_sfm_cv")
            self.assertEqual(binding["metres_per_model_unit"], 1.007804831494465)
            self.assertEqual(binding["input_contract_sha256"], _sha256(input_contract))
            self.assertEqual(binding["reconstruction_list_sha256"], _list_hash(["r0.jpg"]))
            self.assertEqual(binding["heldout_list_sha256"], _list_hash(["f0.jpg"]))
            self.assertEqual(binding["route_semantic_manifest_sha256"], "a" * 64)
            self.assertEqual(len(binding["heldout_semantic_manifest_sha256"]), 64)

    def test_optimized_metric_and_raw_lapa_frames_are_all_contract_owned(self):
        import pw_mesh_bench

        cases = (
            ("optimized_sfm_cv", 1.007804831494465),
            ("metric_arkit_cv", 1.0),
            ("raw_lapa_model", 0.21677133346045502),
        )
        for coordinate_frame, scale in cases:
            with self.subTest(coordinate_frame=coordinate_frame), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                archive, prepared, contract, route, input_contract = _write_binding_fixture(
                    root,
                    self.fixture(),
                    coordinate_frame=coordinate_frame,
                    metres_per_model_unit=scale,
                )
                binding, profile, _ = pw_mesh_bench._validate_experiment_binding(
                    arrays=pw_mesh_bench._load_contract_archive(archive),
                    frames_path=archive,
                    prepared_provenance_path=prepared,
                    preregistered_contract_path=contract,
                    input_contract_path=input_contract,
                    split_id="fixture_1r1h_strict",
                    route_provenance_path=route,
                )
                self.assertEqual(binding["coordinate_frame"], coordinate_frame)
                self.assertEqual(binding["metres_per_model_unit"], scale)
                self.assertEqual(profile["coverage_delta_min"], -0.02)

    def test_wrong_frame_scale_and_split_are_rejected(self):
        import pw_mesh_bench

        mutations = (
            ("prepared_frame", "coordinate_scale", "stored_coordinate_frame", "metric_arkit_cv"),
            ("prepared_scale", "coordinate_scale", "metres_per_model_unit", 1.0),
            ("route_frame", None, "coordinate_frame", "metric_arkit_cv"),
            ("route_scale", None, "metres_per_model_unit", 1.0),
        )
        for label, parent, key, value in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                archive, prepared, contract, route, input_contract = _write_binding_fixture(
                    root, self.fixture()
                )
                target_path = prepared if label.startswith("prepared") else route
                payload = json.loads(target_path.read_text())
                target = payload if parent is None else payload[parent]
                target[key] = value
                target_path.write_text(json.dumps(payload))
                with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                    pw_mesh_bench._validate_experiment_binding(
                        arrays=pw_mesh_bench._load_contract_archive(archive),
                        frames_path=archive,
                        prepared_provenance_path=prepared,
                        preregistered_contract_path=contract,
                        input_contract_path=input_contract,
                        split_id="fixture_1r1h_strict",
                        route_provenance_path=route,
                    )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                pw_mesh_bench._validate_experiment_binding(
                    arrays=pw_mesh_bench._load_contract_archive(archive),
                    frames_path=archive,
                    prepared_provenance_path=prepared,
                    preregistered_contract_path=contract,
                    input_contract_path=input_contract,
                    split_id="different_split",
                    route_provenance_path=route,
                )

    def test_prepared_and_route_contract_hashes_cannot_be_overridden(self):
        import pw_mesh_bench

        for target_kind in ("prepared", "route"):
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                archive, prepared, contract, route, input_contract = _write_binding_fixture(
                    root, self.fixture()
                )
                target_path = prepared if target_kind == "prepared" else route
                payload = json.loads(target_path.read_text())
                if target_kind == "prepared":
                    payload["component_sha256"]["input_contract"] = "f" * 64
                else:
                    payload["frozen_input_identity_contract"]["sha256"] = "f" * 64
                target_path.write_text(json.dumps(payload))
                with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                    pw_mesh_bench._validate_experiment_binding(
                        arrays=pw_mesh_bench._load_contract_archive(archive),
                        frames_path=archive,
                        prepared_provenance_path=prepared,
                        preregistered_contract_path=contract,
                        input_contract_path=input_contract,
                        split_id="fixture_1r1h_strict",
                        route_provenance_path=route,
                    )

    def test_alicevision_provenance_binds_nested_split_without_applying_sim3(self):
        import pw_mesh_bench

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            payload = json.loads(route.read_text())
            payload["schema"] = "pocketworld-b0-alicevision-export-v1"
            del payload["split_id"]
            del payload["coordinate_transform"]
            payload["frozen_sim3_model_to_arkit"] = {
                "canonical_sha256": (
                    "ca5e4b72dcb4e6a7bee8af8182c2947e006de5a59e8ca7c1e030ffee288b70f4"
                ),
                "applied_by_adapter": False,
                "applicable": False,
                "application_stage": (
                    "not_applicable_optimized_sfm_cv_uses_contract_scale_"
                    "without_adapter_alignment"
                ),
            }
            route.write_text(json.dumps(payload))
            binding, _, _ = pw_mesh_bench._validate_experiment_binding(
                arrays=pw_mesh_bench._load_contract_archive(archive),
                frames_path=archive,
                prepared_provenance_path=prepared,
                preregistered_contract_path=contract,
                input_contract_path=input_contract,
                split_id="fixture_1r1h_strict",
                route_provenance_path=route,
            )
            self.assertEqual(binding["coordinate_frame"], "optimized_sfm_cv")
            self.assertEqual(binding["split_id"], "fixture_1r1h_strict")

    def test_mutated_prepared_provenance_fields_are_rejected(self):
        import pw_mesh_bench

        fields = [
            ("component_sha256", "reconstruction_list", "f" * 64),
            ("component_sha256", "heldout_list", "f" * 64),
            ("component_sha256", "dmcache", "f" * 64),
            ("component_sha256", "model_cache", "f" * 64),
            ("component_sha256", "mesh_ab_eval.py", "f" * 64),
            ("component_sha256", "b0_prepare_eval.py", "f" * 64),
            ("semantic_manifest_sha256", "reconstruction", "f" * 64),
            ("semantic_manifest_sha256", "heldout", "f" * 64),
            (None, "evaluation_digest", "f" * 64),
        ]
        for parent, key, value in fields:
            with self.subTest(parent=parent, key=key), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                archive, prepared, contract, route, input_contract = _write_binding_fixture(
                    root, self.fixture()
                )
                payload = json.loads(prepared.read_text())
                target = payload if parent is None else payload[parent]
                target[key] = value
                prepared.write_text(json.dumps(payload))
                with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                    pw_mesh_bench._validate_experiment_binding(
                        arrays=pw_mesh_bench._load_contract_archive(archive),
                        frames_path=archive,
                        prepared_provenance_path=prepared,
                        preregistered_contract_path=contract,
                        input_contract_path=input_contract,
                        split_id="fixture_1r1h_strict",
                        route_provenance_path=route,
                    )


class MonitorBindingTests(unittest.TestCase):
    @staticmethod
    def fixture():
        return {
            "frames": np.array(["f0.jpg"]),
            "depth": np.full((1, 3, 3), 2.0, np.float32),
            "K": np.eye(3, dtype=np.float64)[None],
            "w2c": np.eye(4, dtype=np.float64)[None],
            "roi": np.ones((1, 3, 3), bool),
            "low_texture": np.ones((1, 3, 3), bool),
            "weak_support": np.ones((1, 3, 3), bool),
            "planar_single_surface": np.ones((1, 3, 3), bool),
        }

    def test_tsdf_and_alicevision_monitor_statuses_bind_exact_mesh(self):
        import pw_mesh_bench

        for phase in ("tsdf_meshing", "fusecut_meshing"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as td:
                root = Path(td).resolve()
                _archive, _prepared, contract, route, _input = _write_binding_fixture(
                    root, self.fixture()
                )
                mesh = (root / ("mesh.ply" if phase == "tsdf_meshing" else "mesh.obj")).resolve()
                mesh.write_bytes(b"frozen mesh bytes")
                if phase == "tsdf_meshing":
                    _bind_tsdf_route_mesh(route, mesh)
                else:
                    payload = json.loads(route.read_text())
                    payload["schema"] = "pocketworld-b0-alicevision-export-v1"
                    payload.pop("coordinate_transform")
                    payload.pop("split_id")
                    route.write_text(json.dumps(payload))
                status = _write_monitor_status(
                    root,
                    contract_path=contract,
                    mesh_path=mesh,
                    phase=phase,
                    name=f"monitor-{phase}",
                )
                identity = pw_mesh_bench._validate_route_monitor_status(
                    mesh_path=mesh,
                    monitor_status_path=status,
                    route_provenance_path=route,
                    preregistered_contract_path=contract,
                )
                self.assertEqual(identity["phase"], phase)
                self.assertEqual(identity["attested_mesh"]["sha256"], _sha256(mesh))

    def test_monitor_failure_replacement_and_attestation_drift_are_rejected(self):
        import pw_mesh_bench

        mutations = (
            ("verdict", lambda payload, _root: payload.__setitem__("verdict", "COMMAND_FAILED")),
            (
                "phase",
                lambda payload, _root: payload["formal_binding"].__setitem__(
                    "phase", "fusecut_meshing"
                ),
            ),
            (
                "contract",
                lambda payload, _root: payload["formal_binding"].__setitem__(
                    "contract_sha256", "f" * 64
                ),
            ),
            (
                "argv",
                lambda payload, _root: payload["command"].__setitem__(
                    "argv", ["replacement"]
                ),
            ),
            (
                "environment",
                lambda payload, _root: payload["formal_binding"].__setitem__(
                    "environment_sha256", "f" * 64
                ),
            ),
            (
                "binary",
                lambda payload, _root: payload["formal_binding"].__setitem__(
                    "alicevision_binary_sha256", "f" * 64
                ),
            ),
            (
                "missing_mesh_attestation",
                lambda payload, _root: payload["attestation"].__setitem__("files", []),
            ),
            (
                "wrong_mesh_path",
                lambda payload, root: payload["attestation"]["files"][0].__setitem__(
                    "path", str(root / "replacement.ply")
                ),
            ),
            (
                "wrong_mesh_size",
                lambda payload, _root: payload["attestation"]["files"][0].__setitem__(
                    "size_bytes", 999
                ),
            ),
            (
                "wrong_mesh_sha",
                lambda payload, _root: payload["attestation"]["files"][0].__setitem__(
                    "sha256", "f" * 64
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td).resolve()
                _archive, _prepared, contract, route, _input = _write_binding_fixture(
                    root, self.fixture()
                )
                mesh = (root / "mesh.ply").resolve()
                mesh.write_bytes(b"frozen mesh bytes")
                _bind_tsdf_route_mesh(route, mesh)
                status = _write_monitor_status(
                    root,
                    contract_path=contract,
                    mesh_path=mesh,
                    phase="tsdf_meshing",
                    name="monitor",
                )
                payload = json.loads(status.read_text())
                mutate(payload, root)
                status.write_text(json.dumps(payload))
                with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                    pw_mesh_bench._validate_route_monitor_status(
                        mesh_path=mesh,
                        monitor_status_path=status,
                        route_provenance_path=route,
                        preregistered_contract_path=contract,
                    )

    def test_current_mesh_and_tsdf_provenance_must_match_monitor(self):
        import pw_mesh_bench

        for mode in ("mesh_changed", "provenance_sha_changed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as td:
                root = Path(td).resolve()
                _archive, _prepared, contract, route, _input = _write_binding_fixture(
                    root, self.fixture()
                )
                mesh = (root / "mesh.ply").resolve()
                mesh.write_bytes(b"frozen mesh bytes")
                _bind_tsdf_route_mesh(route, mesh)
                status = _write_monitor_status(
                    root,
                    contract_path=contract,
                    mesh_path=mesh,
                    phase="tsdf_meshing",
                    name="monitor",
                )
                if mode == "mesh_changed":
                    mesh.write_bytes(b"replacement mesh bytes")
                else:
                    payload = json.loads(route.read_text())
                    payload["mesh"]["sha256"] = "f" * 64
                    route.write_text(json.dumps(payload))
                with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
                    pw_mesh_bench._validate_route_monitor_status(
                        mesh_path=mesh,
                        monitor_status_path=status,
                        route_provenance_path=route,
                        preregistered_contract_path=contract,
                    )


class CliFixtureTests(unittest.TestCase):
    @staticmethod
    def fixture():
        return {
            "frames": np.array(["f0.jpg"]),
            "depth": np.full((1, 3, 3), 2.0, np.float32),
            "K": np.eye(3, dtype=np.float64)[None],
            "w2c": np.eye(4, dtype=np.float64)[None],
            "roi": np.ones((1, 3, 3), bool),
            "low_texture": np.ones((1, 3, 3), bool),
            "weak_support": np.ones((1, 3, 3), bool),
            "planar_single_surface": np.ones((1, 3, 3), bool),
        }

    @staticmethod
    def route_result(
        binding,
        *,
        monitor_identity,
        mesh_path: Path,
        route_provenance_path: Path,
    ):
        import mesh_ab_eval

        metrics = {
            "coverage_all": 1.0,
            "coverage_low_texture": 1.0,
            "coverage_weak_support": 1.0,
            "unsupported_over_hits": 0.0,
            "absrel_median_pp": 0.0,
            "absrel_p95_pp": 0.0,
            "normal_median_deg": 0.0,
            "double_shell_rate": 0.0,
            "double_shell_p95_mm": None,
        }
        return {
            "schema": "pocketworld.mesh-ab.route-evaluation.v1",
            "contract_digest": binding["route_semantic_manifest_sha256"],
            "evaluation_digest": binding["evaluation_digest"],
            "dataset_id": binding["dataset_id"],
            "split_id": binding["split_id"],
            "experiment_binding": binding,
            "coordinate_frame": binding["coordinate_frame"],
            "mesh_frame": binding["coordinate_frame"],
            "metric_scale": "contract_model_units",
            "unit_contract": mesh_ab_eval.metric_unit_contract(
                coordinate_frame=binding["coordinate_frame"],
                metres_per_model_unit=binding["metres_per_model_unit"],
                input_contract_sha256=binding["input_contract_sha256"],
                split_id=binding["split_id"],
            ),
            "mesh_path": str(mesh_path.resolve()),
            "mesh_size_bytes": mesh_path.stat().st_size,
            "mesh_sha256": _sha256(mesh_path),
            "route_provenance_path": str(route_provenance_path.resolve()),
            "route_provenance_sha256": _sha256(route_provenance_path),
            "route_monitor_status": monitor_identity,
            "metrics": metrics,
            "frame_counts": {
                name: [{"numerator": 1, "denominator": 1}]
                for name in ("all", "low_texture", "weak_support", "union")
            },
            "topology": {
                "finite": True,
                "degenerate": False,
                "nonmanifold_edge_ratio": 0.0,
            },
        }

    def route_results(self, root, binding, contract, tsdf_route):
        import pw_mesh_bench

        tsdf_mesh = (root / "tsdf-mesh.ply").resolve()
        tsdf_mesh.write_bytes(b"tsdf frozen mesh")
        _bind_tsdf_route_mesh(tsdf_route, tsdf_mesh)
        tsdf_status = _write_monitor_status(
            root,
            contract_path=contract,
            mesh_path=tsdf_mesh,
            phase="tsdf_meshing",
            name="tsdf-monitor",
        )
        tsdf_identity = pw_mesh_bench._validate_route_monitor_status(
            mesh_path=tsdf_mesh,
            monitor_status_path=tsdf_status,
            route_provenance_path=tsdf_route,
            preregistered_contract_path=contract,
        )

        fuse_route = (root / "fuse-route.json").resolve()
        fuse_payload = json.loads(tsdf_route.read_text())
        fuse_payload["schema"] = "pocketworld-b0-alicevision-export-v1"
        fuse_payload.pop("coordinate_transform")
        fuse_payload.pop("split_id")
        fuse_payload.pop("mesh")
        fuse_route.write_text(json.dumps(fuse_payload))
        fuse_mesh = (root / "fuse-mesh.obj").resolve()
        fuse_mesh.write_bytes(b"fusecut frozen mesh")
        fuse_status = _write_monitor_status(
            root,
            contract_path=contract,
            mesh_path=fuse_mesh,
            phase="fusecut_meshing",
            name="fuse-monitor",
        )
        fuse_identity = pw_mesh_bench._validate_route_monitor_status(
            mesh_path=fuse_mesh,
            monitor_status_path=fuse_status,
            route_provenance_path=fuse_route,
            preregistered_contract_path=contract,
        )
        return (
            self.route_result(
                binding,
                monitor_identity=tsdf_identity,
                mesh_path=tsdf_mesh,
                route_provenance_path=tsdf_route,
            ),
            self.route_result(
                binding,
                monitor_identity=fuse_identity,
                mesh_path=fuse_mesh,
                route_provenance_path=fuse_route,
            ),
        )

    def test_bound_quality_compare_round_trip(self):
        import pw_mesh_bench

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            binding, _, _ = pw_mesh_bench._validate_experiment_binding(
                arrays=pw_mesh_bench._load_contract_archive(archive),
                frames_path=archive,
                prepared_provenance_path=prepared,
                preregistered_contract_path=contract,
                input_contract_path=input_contract,
                split_id="fixture_1r1h_strict",
                route_provenance_path=route,
            )
            tsdf = root / "tsdf.json"
            fuse = root / "fuse.json"
            tsdf_result, fuse_result = self.route_results(
                root, binding, contract, route
            )
            tsdf.write_text(json.dumps(tsdf_result))
            fuse.write_text(json.dumps(fuse_result))

            comparison = root / "comparison.json"
            proc = subprocess.run([
                sys.executable, str(PYTHON_TOOLS / "pw_mesh_bench.py"), "compare",
                "--tsdf", str(tsdf), "--fusecut", str(fuse),
                "--frames", str(archive),
                "--prepared-provenance", str(prepared),
                "--preregistered-contract", str(contract),
                "--input-contract", str(input_contract),
                "--split-id", "fixture_1r1h_strict",
                "--out", str(comparison),
            ], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(comparison.read_text())
            self.assertEqual(payload["verdict"], "INCONCLUSIVE")
            self.assertEqual(payload["reason"], "NOT_PROVEN_BETTER")
            self.assertNotIn("nondegenerate", payload["gates"])
            self.assertEqual(payload["evaluation_digest"], binding["evaluation_digest"])
            self.assertEqual(payload["dataset_id"], "fixture_quality")
            self.assertEqual(payload["profile"]["coverage_delta_pp_min"], -2.0)
            self.assertEqual(payload["bootstrap"]["weak_support"]["replicates"], 10_000)
            self.assertEqual(payload["metric_scale"], "contract_model_units")
            self.assertEqual(payload["coordinate_frame"], "optimized_sfm_cv")
            self.assertEqual(
                payload["unit_contract"]["metres_per_model_unit"],
                1.007804831494465,
            )
            self.assertFalse(payload["unit_contract"]["applied_to_geometry"])
            self.assertTrue(payload["unit_contract"]["used_only_for_metric_unit_conversion"])
            self.assertEqual(
                payload["route_monitor_statuses"]["tsdf"]["phase"],
                "tsdf_meshing",
            )
            self.assertEqual(
                payload["route_monitor_statuses"]["fusecut"]["phase"],
                "fusecut_meshing",
            )

            forged_tsdf = root / "forged-tsdf.json"
            forged_result = json.loads(json.dumps(tsdf_result))
            forged_result["route_monitor_status"]["child_argv_sha256"] = "f" * 64
            forged_tsdf.write_text(json.dumps(forged_result))
            forged_output = root / "forged-comparison.json"
            forged = subprocess.run([
                sys.executable, str(PYTHON_TOOLS / "pw_mesh_bench.py"), "compare",
                "--tsdf", str(forged_tsdf), "--fusecut", str(fuse),
                "--frames", str(archive),
                "--prepared-provenance", str(prepared),
                "--preregistered-contract", str(contract),
                "--input-contract", str(input_contract),
                "--split-id", "fixture_1r1h_strict",
                "--out", str(forged_output),
            ], text=True, capture_output=True)
            self.assertNotEqual(forged.returncode, 0)
            self.assertFalse(forged_output.exists())
            self.assertIn("ROUTE_INPUT_NOT_EQUIVALENT", forged.stderr)

            nonstandard = root / "nonstandard.json"
            rejected = subprocess.run([
                sys.executable, str(PYTHON_TOOLS / "pw_mesh_bench.py"), "compare",
                "--tsdf", str(tsdf), "--fusecut", str(fuse),
                "--frames", str(archive),
                "--prepared-provenance", str(prepared),
                "--preregistered-contract", str(contract),
                "--input-contract", str(input_contract),
                "--split-id", "fixture_1r1h_strict",
                "--bootstrap-replicates", "9999",
                "--out", str(nonstandard),
            ], text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(nonstandard.exists())
            self.assertIn("ROUTE_INPUT_NOT_EQUIVALENT", rejected.stderr)

    def test_evaluate_mesh_cli_requires_and_records_the_full_binding(self):
        try:
            import open3d  # noqa: F401
        except ImportError:
            self.skipTest("Open3D unavailable")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            mesh = (root / "plane.obj").resolve()
            mesh.write_text(
                "v -1 -1 2\n"
                "v 5 -1 2\n"
                "v 5 5 2\n"
                "v -1 5 2\n"
                "v 0 0 2\n"
                "v 1 0 2\n"
                "v 2 0 2\n"
                "f 1 3 2\n"
                "f 1 4 3\n"
                "f 5 6 7\n"
            )
            _bind_tsdf_route_mesh(route, mesh)
            monitor_status = _write_monitor_status(
                root,
                contract_path=contract,
                mesh_path=mesh,
                phase="tsdf_meshing",
                name="route-monitor",
            )
            output = root / "evaluated.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(PYTHON_TOOLS / "pw_mesh_bench.py"),
                    "evaluate-mesh",
                    "--frames",
                    str(archive),
                    "--mesh",
                    str(mesh),
                    "--mesh-frame",
                    "contract_model",
                    "--route-provenance",
                    str(route),
                    "--route-monitor-status",
                    str(monitor_status),
                    "--prepared-provenance",
                    str(prepared),
                    "--preregistered-contract",
                    str(contract),
                    "--input-contract",
                    str(input_contract),
                    "--split-id",
                    "fixture_1r1h_strict",
                    "--out",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["dataset_id"], "fixture_quality")
            self.assertEqual(payload["mesh_frame"], "optimized_sfm_cv")
            self.assertFalse(payload["geometry_transform"]["scale_applied"])
            self.assertFalse(payload["geometry_transform"]["sim3_applied"])
            self.assertFalse(payload["geometry_transform"]["icp_applied"])
            self.assertEqual(len(payload["experiment_binding"]["binding_sha256"]), 64)
            self.assertEqual(payload["contract_digest"], "a" * 64)
            self.assertEqual(
                payload["experiment_binding"]["prepared_provenance_sha256"],
                _sha256(prepared),
            )
            self.assertEqual(payload["alignment"], "none")
            self.assertEqual(
                payload["route_monitor_status"]["phase"], "tsdf_meshing"
            )
            self.assertEqual(
                payload["route_monitor_status"]["status_sha256"],
                _sha256(monitor_status),
            )
            self.assertEqual(payload["topology"]["zero_area_face_count"], 1)
            self.assertEqual(payload["evaluation_face_filter"]["input_face_count"], 3)
            self.assertEqual(payload["evaluation_face_filter"]["excluded_face_count"], 1)
            self.assertEqual(payload["evaluation_face_filter"]["evaluated_face_count"], 2)

    def test_evaluate_mesh_rejects_failed_or_missing_monitor_before_output(self):
        try:
            import open3d  # noqa: F401
        except ImportError:
            self.skipTest("Open3D unavailable")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            mesh = (root / "plane.obj").resolve()
            mesh.write_text(
                "v -1 -1 2\n"
                "v 5 -1 2\n"
                "v 5 5 2\n"
                "v -1 5 2\n"
                "f 1 3 2\n"
                "f 1 4 3\n"
            )
            _bind_tsdf_route_mesh(route, mesh)
            status = _write_monitor_status(
                root,
                contract_path=contract,
                mesh_path=mesh,
                phase="tsdf_meshing",
                name="failed-monitor",
            )
            status_payload = json.loads(status.read_text())
            status_payload["verdict"] = "COMMAND_FAILED"
            status.write_text(json.dumps(status_payload))

            common = [
                sys.executable,
                str(PYTHON_TOOLS / "pw_mesh_bench.py"),
                "evaluate-mesh",
                "--frames",
                str(archive),
                "--mesh",
                str(mesh),
                "--mesh-frame",
                "contract_model",
                "--route-provenance",
                str(route),
                "--prepared-provenance",
                str(prepared),
                "--preregistered-contract",
                str(contract),
                "--input-contract",
                str(input_contract),
                "--split-id",
                "fixture_1r1h_strict",
            ]
            failed_output = root / "failed.json"
            failed = subprocess.run(
                common
                + [
                    "--route-monitor-status",
                    str(status),
                    "--out",
                    str(failed_output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(failed_output.exists())
            self.assertIn("ROUTE_INPUT_NOT_EQUIVALENT", failed.stderr)

            missing_output = root / "missing.json"
            missing = subprocess.run(
                common + ["--out", str(missing_output)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(missing_output.exists())
            self.assertIn("--route-monitor-status", missing.stderr)

    def test_compare_digest_failure_writes_no_gate_numbers(self):
        import pw_mesh_bench

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive, prepared, contract, route, input_contract = _write_binding_fixture(
                root, self.fixture()
            )
            binding, _, _ = pw_mesh_bench._validate_experiment_binding(
                arrays=pw_mesh_bench._load_contract_archive(archive),
                frames_path=archive,
                prepared_provenance_path=prepared,
                preregistered_contract_path=contract,
                input_contract_path=input_contract,
                split_id="fixture_1r1h_strict",
                route_provenance_path=route,
            )
            tsdf_result, fuse_result = self.route_results(
                root, binding, contract, route
            )
            tsdf = root / "tsdf.json"; fuse = root / "fuse.json"
            tsdf.write_text(json.dumps(tsdf_result))
            fuse.write_text(
                json.dumps({**fuse_result, "contract_digest": "f" * 64})
            )
            out = root / "comparison.json"
            proc = subprocess.run([
                sys.executable, str(PYTHON_TOOLS / "pw_mesh_bench.py"), "compare",
                "--tsdf", str(tsdf), "--fusecut", str(fuse),
                "--frames", str(archive),
                "--prepared-provenance", str(prepared),
                "--preregistered-contract", str(contract),
                "--input-contract", str(input_contract),
                "--split-id", "fixture_1r1h_strict", "--out", str(out),
            ], text=True, capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(out.exists())
            self.assertIn("ROUTE_INPUT_NOT_EQUIVALENT", proc.stderr)

    def test_route_provenance_digest_is_read_from_actual_adapter_output(self):
        import pw_mesh_bench

        self.assertEqual(
            pw_mesh_bench._route_manifest_digest(
                {"semantic_manifest_sha256": "a" * 64}
            ),
            "a" * 64,
        )
        self.assertEqual(
            pw_mesh_bench._route_manifest_digest(
                {"input_equivalence_contract": {"semantic_manifest_sha256": "b" * 64}}
            ),
            "b" * 64,
        )
        with self.assertRaises(pw_mesh_bench.E.EvaluationContractError):
            pw_mesh_bench._route_manifest_digest({})
        self.assertEqual(
            pw_mesh_bench._route_frame_list_digest(
                {"frame_list_sha256": "c" * 64}
            ),
            "c" * 64,
        )
        self.assertEqual(
            pw_mesh_bench._route_frame_list_digest(
                {"inputs": {"frame_list": {"file_sha256": "d" * 64}}}
            ),
            "d" * 64,
        )


if __name__ == "__main__":
    unittest.main()
