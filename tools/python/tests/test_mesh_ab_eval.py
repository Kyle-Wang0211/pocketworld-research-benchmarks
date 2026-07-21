from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
if str(PYTHON_TOOLS) not in sys.path:
    sys.path.insert(0, str(PYTHON_TOOLS))

import mesh_ab_eval as subject  # noqa: E402


class FrozenInputContractTests(unittest.TestCase):
    def fixture(self):
        return {
            "frames": np.array(["f0.jpg", "f1.jpg"]),
            "depth": np.ones((2, 3, 4), dtype=np.float32),
            "K": np.repeat(np.eye(3, dtype=np.float64)[None], 2, axis=0),
            "w2c": np.repeat(np.eye(4, dtype=np.float64)[None], 2, axis=0),
            "roi": np.ones((2, 3, 4), dtype=bool),
            "low_texture": np.zeros((2, 3, 4), dtype=bool),
            "weak_support": np.zeros((2, 3, 4), dtype=bool),
            "planar_single_surface": np.ones((2, 3, 4), dtype=bool),
        }

    def test_digest_is_stable_and_bit_sensitive(self):
        a = self.fixture()
        b = {key: value.copy() for key, value in a.items()}
        digest = subject.frozen_input_digest(a)
        self.assertEqual(digest, "a6b17408d2cbe5ac57ff0ff8469fb9868cf52e50b52b847f53e8abe6dbf9740e")
        self.assertEqual(digest, subject.frozen_input_digest(b))
        self.assertEqual(len(digest), 64)
        b["depth"].view(np.uint8).reshape(-1)[0] ^= 1
        self.assertNotEqual(digest, subject.frozen_input_digest(b))

    def test_every_contract_member_is_bound(self):
        base = self.fixture()
        expected = subject.frozen_input_digest(base)
        for key in base:
            changed = {name: value.copy() for name, value in base.items()}
            if key == "frames":
                changed[key][0] = "x0.jpg"
            elif changed[key].dtype == bool:
                changed[key].reshape(-1)[0] ^= True
            else:
                changed[key].view(np.uint8).reshape(-1)[0] ^= 1
            with self.subTest(key=key):
                self.assertNotEqual(expected, subject.frozen_input_digest(changed))

    def test_route_digest_mismatch_has_exact_code(self):
        with self.assertRaises(subject.EvaluationContractError) as caught:
            subject.require_equivalent_route_inputs("expected", "expected", "different")
        self.assertEqual(caught.exception.code, "ROUTE_INPUT_NOT_EQUIVALENT")


class CoordinateFrameTests(unittest.TestCase):
    CONTRACT_SHA256 = "c" * 64
    SPLIT_ID = "cap50_93r22h_strict"

    def test_alicevision_obj_is_decoded_into_contract_model_frame(self):
        stored = np.array([[1.0, 2.0, 3.0], [-1.0, -2.0, -3.0]])
        actual = subject.vertices_to_contract_model(stored, "alicevision_obj")
        np.testing.assert_array_equal(actual, [[1.0, -2.0, -3.0], [-1.0, 2.0, 3.0]])

    def test_contract_model_is_unchanged_and_unknown_is_rejected(self):
        vertices = np.array([[1.0, 2.0, 3.0]])
        np.testing.assert_array_equal(
            subject.vertices_to_contract_model(vertices, "contract_model"), vertices
        )
        with self.assertRaises(subject.EvaluationContractError) as caught:
            subject.vertices_to_contract_model(vertices, "arkit")
        self.assertEqual(caught.exception.code, "COORDINATE_FRAME_MISMATCH")

    def test_optimized_sfm_scale_is_contract_owned_and_never_applied_to_geometry(self):
        scale = 1.007804831494465
        frozen = subject.metric_unit_contract(
            coordinate_frame="optimized_sfm_cv",
            metres_per_model_unit=scale,
            input_contract_sha256=self.CONTRACT_SHA256,
            split_id=self.SPLIT_ID,
        )
        subject.require_matching_metric_unit_contracts(
            frozen,
            dict(frozen),
            coordinate_frame="optimized_sfm_cv",
            metres_per_model_unit=scale,
            input_contract_sha256=self.CONTRACT_SHA256,
            split_id=self.SPLIT_ID,
        )
        self.assertFalse(frozen["applied_to_geometry"])
        self.assertNotIn("legacy_raw_lapa_frozen_sim3_sha256", frozen)
        self.assertAlmostEqual(
            frozen["thresholds_contract_model_units"]["unsupported_surface"],
            0.020 / scale,
        )
        wrong = dict(frozen)
        wrong["metres_per_model_unit"] = 1.0
        with self.assertRaises(subject.EvaluationContractError) as caught:
            subject.require_matching_metric_unit_contracts(
                frozen,
                wrong,
                coordinate_frame="optimized_sfm_cv",
                metres_per_model_unit=scale,
                input_contract_sha256=self.CONTRACT_SHA256,
                split_id=self.SPLIT_ID,
            )
        self.assertEqual(caught.exception.code, "COORDINATE_FRAME_MISMATCH")

    def test_metric_and_raw_lapa_contracts_retain_their_exact_scales(self):
        metric = subject.metric_unit_contract(
            coordinate_frame="metric_arkit_cv",
            metres_per_model_unit=1.0,
            input_contract_sha256=self.CONTRACT_SHA256,
            split_id=self.SPLIT_ID,
        )
        self.assertEqual(metric["thresholds_contract_model_units"]["planar_residual"], 0.005)
        raw = subject.metric_unit_contract(
            coordinate_frame="raw_lapa_model",
            metres_per_model_unit=subject.FROZEN_METRES_PER_LAPA_UNIT,
            input_contract_sha256=self.CONTRACT_SHA256,
            split_id=self.SPLIT_ID,
        )
        self.assertEqual(
            raw["legacy_raw_lapa_frozen_sim3_sha256"], subject.FROZEN_SIM3_SHA256
        )
        self.assertFalse(raw["legacy_raw_lapa_sim3_applied_by_evaluator"])
        with self.assertRaises(subject.EvaluationContractError):
            subject.metric_unit_contract(
                coordinate_frame="raw_lapa_model",
                metres_per_model_unit=1.0,
                input_contract_sha256=self.CONTRACT_SHA256,
                split_id=self.SPLIT_ID,
            )


class MeshTopologyTests(unittest.TestCase):
    def test_plane_cube_and_nonmanifold_ratio(self):
        plane_v = np.array([[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
        plane_f = np.array([[0, 1, 2], [0, 2, 3]], np.int64)
        plane = subject.mesh_topology_metrics(plane_v, plane_f)
        self.assertTrue(plane["finite"])
        self.assertFalse(plane["degenerate"])
        self.assertEqual(plane["zero_area_face_count"], 0)
        self.assertEqual(plane["valid_face_count"], 2)
        self.assertEqual(plane["nonmanifold_edge_ratio"], 0.0)

        cube_v = np.array(
            [[x, y, z] for z in (2, 3) for y in (0, 1) for x in (0, 1)], float
        )
        cube_f = np.array(
            [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
             [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
             [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]], np.int64
        )
        self.assertEqual(subject.mesh_topology_metrics(cube_v, cube_f)["nonmanifold_edge_ratio"], 0.0)

        # Edge (0,1) has incidence 3; the seven unique edges give ratio 1/7.
        nm_v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1]], float)
        nm_f = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], np.int64)
        self.assertAlmostEqual(
            subject.mesh_topology_metrics(nm_v, nm_f)["nonmanifold_edge_ratio"], 1 / 7
        )

    def test_empty_single_triangle_nonfinite_bad_index_and_zero_area(self):
        cases = [
            (np.empty((0, 3)), np.empty((0, 3), np.int64), "empty"),
            (np.array([[0, 0, 1], [1, 0, 1], [0, 1, 1]], float), np.array([[0, 1, 2]]), "single_triangle"),
            (np.array([[0, 0, 1], [1, 0, 1], [0, np.nan, 1]], float), np.array([[0, 1, 2]]), "nonfinite"),
            (np.array([[0, 0, 1], [1, 0, 1], [0, 1, 1]], float), np.array([[0, 1, 3]]), "bad_index"),
            (np.array([[0, 0, 1], [1, 0, 1], [2, 0, 1]], float), np.array([[0, 1, 2]]), "zero_area"),
        ]
        for vertices, faces, reason in cases:
            with self.subTest(reason=reason):
                metrics = subject.mesh_topology_metrics(vertices, faces)
                self.assertTrue(metrics["degenerate"])
                self.assertIn(reason, metrics["degenerate_reasons"])

        zero_area = subject.mesh_topology_metrics(
            np.array(
                [[0, 0, 1], [1, 0, 1], [2, 0, 1], [0, 1, 1], [1, 1, 1]],
                float,
            ),
            np.array([[0, 1, 2], [0, 3, 4]], np.int64),
        )
        self.assertEqual(zero_area["zero_area_face_count"], 1)
        self.assertEqual(zero_area["valid_face_count"], 1)

    def test_shared_face_sanitation_matches_explicit_removal_and_rejects_all_zero(self):
        vertices = np.array(
            [[0, 0, 1], [1, 0, 1], [2, 0, 1], [0, 1, 1], [1, 1, 1], [0, 2, 1]],
            float,
        )
        faces = np.array([[0, 1, 2], [0, 3, 4], [0, 4, 5]], np.int64)
        filtered, audit = subject.sanitize_evaluation_faces(vertices, faces)
        np.testing.assert_array_equal(filtered, faces[1:])
        self.assertEqual(audit["input_face_count"], 3)
        self.assertEqual(audit["excluded_face_count"], 1)
        self.assertEqual(audit["evaluated_face_count"], 2)
        self.assertTrue(audit["applied_identically_to_both_routes"])

        with self.assertRaises(subject.EvaluationContractError) as caught:
            subject.sanitize_evaluation_faces(vertices[:3], np.array([[0, 1, 2], [2, 1, 0]]))
        self.assertEqual(caught.exception.code, subject.METRIC_UNDEFINED)


class ObservationMetricTests(unittest.TestCase):
    def test_physical_thresholds_are_converted_to_model_units(self):
        self.assertAlmostEqual(
            subject.physical_metres_to_model_units(0.020, metres_per_model_unit=0.2),
            0.1,
        )
        np.testing.assert_allclose(
            subject.depth_tolerance(np.array([1.0]), metres_per_model_unit=0.2),
            [0.1],
        )
        masks = {
            name: np.ones((1, 1), bool)
            for name in ("roi", "low_texture", "weak_support")
        }
        below = subject.evaluate_frame_observations(
            np.array([[2.0]]), np.array([[1.91]]), masks=masks,
            metres_per_model_unit=0.2,
        )
        above = subject.evaluate_frame_observations(
            np.array([[2.0]]), np.array([[1.89]]), masks=masks,
            metres_per_model_unit=0.2,
        )
        self.assertEqual(below["all"]["unsupported_numerator"], 0)
        self.assertEqual(above["all"]["unsupported_numerator"], 1)

    def test_ray_parameter_is_explicitly_converted_to_camera_z(self):
        # Unit diagonal ray reaches z=2 at Euclidean t=2*sqrt(2).
        t = np.array([2.0 * np.sqrt(2.0), np.inf])
        directions = np.array([[1, 0, 1], [0, 0, 1]], float) / np.array([[np.sqrt(2)], [1]])
        converted = subject.ray_parameter_to_camera_z(t, directions)
        self.assertAlmostEqual(converted[0], 2.0)
        self.assertTrue(np.isinf(converted[1]))

    def test_plane_and_offset_plane_metrics(self):
        z = np.full((5, 5), 2.0)
        hit = z.copy()
        masks = {name: np.ones_like(z, bool) for name in ("roi", "low_texture", "weak_support")}
        frame = subject.evaluate_frame_observations(
            z, hit, masks=masks, metres_per_model_unit=1.0
        )
        self.assertEqual(frame["all"]["coverage_numerator"], 25)
        self.assertEqual(frame["all"]["coverage_denominator"], 25)
        self.assertTrue(np.allclose(frame["all"]["absrel_values"], 0))

        # tau=max(20 mm, 2%*2 m)=40 mm: +30 mm stays covered.
        offset = subject.evaluate_frame_observations(
            z, z + 0.03, masks=masks, metres_per_model_unit=1.0
        )
        self.assertEqual(offset["all"]["coverage_numerator"], 25)
        self.assertAlmostEqual(np.median(offset["all"]["absrel_values"]) * 100, 1.5)

        front = subject.evaluate_frame_observations(
            z, z - 0.03, masks=masks, metres_per_model_unit=1.0
        )
        self.assertEqual(front["all"]["unsupported_numerator"], 25)
        self.assertEqual(front["all"]["unsupported_hit_denominator"], 25)

    def test_observation_normals_require_valid_smooth_four_neighbourhood(self):
        z = np.full((5, 5), 2.0)
        normals, valid = subject.observed_normals_camera_z(z, np.eye(3))
        self.assertEqual(int(valid.sum()), 9)
        np.testing.assert_allclose(normals[2, 2], [0, 0, -1], atol=1e-8)
        z[2, 1] = 0
        _, valid = subject.observed_normals_camera_z(z, np.eye(3))
        self.assertFalse(valid[2, 2])


class DoubleShellTests(unittest.TestCase):
    def test_cube_front_and_back_are_not_reported(self):
        result = subject.double_shell_metrics(
            observed_z=np.array([2.0]),
            intersections_z=[np.array([2.0, 3.0])],
            intersection_normals=[np.array([[0, 0, -1], [0, 0, 1]], float)],
            eligible_mask=np.array([True]),
            metres_per_model_unit=1.0,
        )
        self.assertEqual(result["eligible_rays"], 1)
        self.assertEqual(result["event_count"], 0)
        self.assertIsNone(result["separation_p95_mm"])

    def test_two_near_parallel_planes_are_one_double_shell_event(self):
        result = subject.double_shell_metrics(
            observed_z=np.array([2.0]),
            intersections_z=[np.array([2.0, 2.03004, 2.03001])],
            intersection_normals=[np.array([[0, 0, -1]] * 3, float)],
            eligible_mask=np.array([True]),
            metres_per_model_unit=1.0,
        )
        self.assertEqual(result["eligible_rays"], 1)
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["rate"], 1.0)
        self.assertAlmostEqual(result["separation_p95_mm"], 30.025, places=3)

    def test_same_facing_shells_are_detected_but_opposed_closed_surfaces_are_not(self):
        same_facing = subject.double_shell_metrics(
            observed_z=np.array([2.0]),
            intersections_z=[np.array([2.0, 2.02])],
            intersection_normals=[np.array([[0, 0, -1], [0, 0, -1]], float)],
            eligible_mask=np.array([True]),
            metres_per_model_unit=1.0,
        )
        closed_surface = subject.double_shell_metrics(
            observed_z=np.array([2.0]),
            intersections_z=[np.array([2.0, 2.02])],
            intersection_normals=[np.array([[0, 0, -1], [0, 0, 1]], float)],
            eligible_mask=np.array([True]),
            metres_per_model_unit=1.0,
        )
        self.assertEqual(same_facing["event_count"], 1)
        self.assertEqual(closed_surface["event_count"], 0)

    def test_shell_model_separation_is_reported_in_physical_mm(self):
        result = subject.double_shell_metrics(
            observed_z=np.array([2.0]),
            intersections_z=[np.array([2.0, 2.15])],
            intersection_normals=[np.array([[0, 0, -1], [0, 0, -1]], float)],
            eligible_mask=np.array([True]),
            metres_per_model_unit=0.2,
        )
        self.assertEqual(result["rate"], 1.0)
        self.assertAlmostEqual(result["separation_p95_mm"], 30.0)

    def test_sparse_shell_hits_treat_missing_large_nonplanar_set_as_empty(self):
        ray_count = 250_000
        eligible = np.zeros(ray_count, dtype=bool)
        result = subject.double_shell_metrics(
            observed_z=np.ones(ray_count),
            eligible_mask=eligible,
            sparse_intersections={},
            metres_per_model_unit=0.2,
        )
        self.assertEqual(result["eligible_rays"], 0)
        self.assertEqual(result["event_count"], 0)
        self.assertIsNone(result["rate"])


class BootstrapAndGateTests(unittest.TestCase):
    def counts(self, numerators, denominators):
        return [{"numerator": n, "denominator": d} for n, d in zip(numerators, denominators)]

    def test_identical_paired_bootstrap_is_exactly_zero_and_reproducible(self):
        counts = self.counts([5, 9, 1], [10, 10, 2])
        a = subject.paired_frame_bootstrap(counts, counts, replicates=10_000, seed=20260721)
        b = subject.paired_frame_bootstrap(counts, counts, replicates=10_000, seed=20260721)
        self.assertEqual(a, b)
        self.assertEqual(a["estimate_pp"], 0.0)
        self.assertEqual(a["ci95_pp"], [0.0, 0.0])

    def strict_gate_contract(self):
        return {
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

    def test_every_quality_dataset_uses_prompt_strict_gates(self):
        for dataset_id in (
            "cap100_quality",
            "full413_quality",
            "cap50_115_available_quality",
        ):
            with self.subTest(dataset_id=dataset_id):
                profile = subject.preregistered_gate_profile(
                    dataset_id, self.strict_gate_contract()
                )
                self.assertEqual(profile["coverage_delta_pp_min"], -2.0)
                self.assertEqual(profile["unsupported_delta_pp_max"], 2.0)
                self.assertEqual(profile["absrel_median_delta_pp_max"], 0.5)
                self.assertEqual(profile["absrel_p95_delta_pp_max"], 2.0)
                self.assertEqual(profile["normal_median_delta_deg_max"], 2.0)
                self.assertEqual(profile["double_shell_rate_delta_pp_max"], 1.0)
                self.assertEqual(profile["double_shell_p95_delta_mm_max"], 5.0)
                self.assertEqual(profile["nonmanifold_ratio_max"], 1e-4)
                self.assertTrue(profile["require_double_shell"])

    def test_relaxed_gate_contract_is_rejected_but_dataset_id_is_generic(self):
        relaxed = self.strict_gate_contract()
        relaxed["coverage_delta_min"] = -0.05
        with self.assertRaises(subject.EvaluationContractError):
            subject.preregistered_gate_profile("cap100_quality", relaxed)
        profile = subject.preregistered_gate_profile(
            "cap50_115_available_quality", self.strict_gate_contract()
        )
        self.assertEqual(profile["dataset_id"], "cap50_115_available_quality")

    def test_final_comparison_requires_exact_preregistered_bootstrap(self):
        scale = 1.007804831494465
        input_contract_sha256 = "c" * 64
        split_id = "cap50_93r22h_strict"
        route = {
            "contract_digest": "a" * 64,
            "evaluation_digest": "b" * 64,
            "coordinate_frame": "optimized_sfm_cv",
            "mesh_frame": "optimized_sfm_cv",
            "metric_scale": "contract_model_units",
            "unit_contract": subject.metric_unit_contract(
                coordinate_frame="optimized_sfm_cv",
                metres_per_model_unit=scale,
                input_contract_sha256=input_contract_sha256,
                split_id=split_id,
            ),
            "metrics": {
                "coverage_all": 1.0,
                "coverage_low_texture": 1.0,
                "coverage_weak_support": 1.0,
                "unsupported_over_hits": 0.0,
                "absrel_median_pp": 0.0,
                "absrel_p95_pp": 0.0,
                "normal_median_deg": 0.0,
                "double_shell_rate": 0.0,
                "double_shell_p95_mm": None,
            },
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
        improvement = {
            "bootstrap_draws": 10_000,
            "seed": 20260721,
            "confidence_interval": "two-sided percentile 95%; use lower bound",
            "required_low_texture_coverage_lower_bound": 0.05,
            "required_weak_support_coverage_lower_bound": 0.05,
            "also_requires_all_noninferiority_gates": True,
            "unit": "paired held-out frame",
        }
        for draws, seed in ((9_999, 20260721), (10_000, 7)):
            with self.subTest(draws=draws, seed=seed):
                with self.assertRaises(subject.EvaluationContractError):
                    subject.compare_route_evaluations(
                        route,
                        route,
                        expected_digest="a" * 64,
                        expected_evaluation_digest="b" * 64,
                        dataset_id="cap100_quality",
                        split_id=split_id,
                        coordinate_frame="optimized_sfm_cv",
                        metres_per_model_unit=scale,
                        input_contract_sha256=input_contract_sha256,
                        gate_contract=self.strict_gate_contract(),
                        improvement_contract=improvement,
                        bootstrap_replicates=draws,
                        bootstrap_seed=seed,
                    )

    def test_verdict_semantics(self):
        passed = {"all_noninferiority_pass": True, "required_metrics_defined": True}
        self.assertEqual(subject.decide_verdict(passed, 4.99, 20.0)["verdict"], "INCONCLUSIVE")
        self.assertEqual(subject.decide_verdict(passed, 5.0, 5.0)["verdict"], "PASS")
        failed = {"all_noninferiority_pass": False, "required_metrics_defined": True}
        self.assertEqual(subject.decide_verdict(failed, 10.0, 10.0)["verdict"], "FAIL")
        undefined = {"all_noninferiority_pass": False, "required_metrics_defined": False}
        self.assertEqual(subject.decide_verdict(undefined, 10.0, 10.0)["verdict"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
