import importlib.util
import itertools
import sys
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("fr_planesweep_wall_ceiling.py")
SPEC = importlib.util.spec_from_file_location("fr_planesweep_wall_ceiling", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FIT_MODULE_PATH = Path(__file__).with_name("fit_structural_planes.py")
FIT_SPEC = importlib.util.spec_from_file_location("fit_structural_planes", FIT_MODULE_PATH)
FIT_MODULE = importlib.util.module_from_spec(FIT_SPEC)
assert FIT_SPEC.loader is not None
sys.modules[FIT_SPEC.name] = FIT_MODULE
FIT_SPEC.loader.exec_module(FIT_MODULE)


class PlaneSweepCoreTest(unittest.TestCase):
    def test_scale_rescue_is_wall_only(self):
        self.assertTrue(MODULE.scale_rescue_applies({"kind": "wall"}, 0.06))
        self.assertFalse(MODULE.scale_rescue_applies({"kind": "floor"}, 0.06))
        self.assertFalse(MODULE.scale_rescue_applies({"kind": "ceiling"}, 0.06))
        self.assertFalse(MODULE.scale_rescue_applies({"kind": "wall"}, None))

    def test_largest_consistent_clique_requires_all_pairs(self):
        ncc = np.array(
            [
                [1.0, 0.9, 0.9, 0.9],
                [0.9, 1.0, 0.8, 0.2],
                [0.9, 0.8, 1.0, 0.1],
                [0.9, 0.2, 0.1, 1.0],
            ]
        )
        clique = MODULE.largest_consistent_clique(ncc, 0.7, 3)
        self.assertEqual(clique.tolist(), [0, 1, 2])

    def test_clique_rejects_when_only_star_agrees(self):
        ncc = np.array([[1.0, 0.9, 0.9], [0.9, 1.0, 0.2], [0.9, 0.2, 1.0]])
        self.assertEqual(len(MODULE.largest_consistent_clique(ncc, 0.7, 3)), 0)

    def test_branch_and_bound_clique_matches_bruteforce(self):
        rng = np.random.default_rng(12345)
        for _ in range(25):
            values = rng.uniform(0.0, 1.0, size=(8, 8))
            ncc = (values + values.T) * 0.5
            np.fill_diagonal(ncc, 1.0)
            actual = MODULE.largest_consistent_clique(ncc, 0.55, 3)
            best_size = 0
            best_median = -1.0
            for size in range(3, 9):
                for indices in itertools.combinations(range(8), size):
                    sub = ncc[np.ix_(indices, indices)]
                    upper = sub[np.triu_indices(size, 1)]
                    if np.all(upper >= 0.55):
                        score = (size, float(np.median(upper)))
                        if score > (best_size, best_median):
                            best_size, best_median = score
            self.assertEqual(len(actual), best_size)
            if best_size:
                sub = ncc[np.ix_(actual, actual)]
                actual_median = float(np.median(sub[np.triu_indices(best_size, 1)]))
                self.assertAlmostEqual(actual_median, best_median)

    def test_wall_grid_lies_on_plane_and_height_bounds(self):
        surface = {
            "kind": "wall",
            "normal": [1.0, 0.0, 0.0],
            "plane_value_n_dot_x": 2.0,
            "basis_u": [0.0, 0.0, 1.0],
            "bounds_u_m": [-0.1, 0.1],
            "bounds_height_m": [0.0, 0.2],
        }
        floor = {"normal": [0.0, 1.0, 0.0], "plane_value_n_dot_x": -1.0}
        points = MODULE.surface_grid(surface, floor, 0.1)
        self.assertTrue(np.allclose(points[:, 0], 2.0))
        self.assertEqual(set(np.round(points[:, 1], 6)), {-1.0, -0.9, -0.8})
        self.assertEqual(set(np.round(points[:, 2], 6)), {-0.1, 0.0, 0.1})

    def test_ceiling_offset_probe_moves_only_along_normal(self):
        surface = {
            "kind": "ceiling",
            "normal": [0.0, 1.0, 0.0],
            "plane_value_n_dot_x": 2.0,
            "basis_u": [1.0, 0.0, 0.0],
            "basis_v": [0.0, 0.0, 1.0],
            "bounds_u_m": [0.0, 0.1],
            "bounds_v_m": [0.0, 0.1],
        }
        floor = {"normal": [0.0, 1.0, 0.0], "plane_value_n_dot_x": 0.0}
        base = MODULE.surface_grid(surface, floor, 0.1)
        shifted = MODULE.surface_grid(surface, floor, 0.1, 0.05)
        self.assertTrue(np.allclose(shifted - base, [0.0, 0.05, 0.0]))

    def test_floor_grid_lies_on_known_plane(self):
        floor = {
            "surface_id": "floor_0",
            "kind": "floor",
            "normal": [0.0, 1.0, 0.0],
            "plane_value_n_dot_x": -1.0,
            "basis_u": [1.0, 0.0, 0.0],
            "basis_v": [0.0, 0.0, 1.0],
            "bounds_u_m": [-0.1, 0.1],
            "bounds_v_m": [0.0, 0.2],
            "certified_for_generation": True,
        }
        points = MODULE.surface_grid(floor, floor, 0.1)
        self.assertTrue(np.allclose(points[:, 1], -1.0))
        self.assertEqual(set(np.round(points[:, 0], 6)), {-0.1, 0.0, 0.1})
        self.assertEqual(set(np.round(points[:, 2], 6)), {0.0, 0.1, 0.2})

    def test_surface_selection_includes_certified_floor(self):
        floor = {
            "surface_id": "floor_0",
            "kind": "floor",
            "certified_for_generation": True,
            "bounds_u_m": [0.0, 1.0],
            "bounds_v_m": [0.0, 1.0],
        }
        wall = {
            "surface_id": "wall_0",
            "kind": "wall",
            "certified_for_generation": True,
        }
        selected = MODULE.select_surfaces(
            {"floor": floor, "surfaces": [wall]}, None, allow_uncertified=False
        )
        self.assertEqual([surface["surface_id"] for surface in selected], ["floor_0", "wall_0"])

    def test_floor_domain_is_derived_only_from_on_plane_sparse_support(self):
        xyz = np.array(
            [
                [-1.0, 0.005, 2.0],
                [1.0, -0.005, 4.0],
                [100.0, 1.0, 100.0],
            ]
        )
        floor = FIT_MODULE.build_floor_surface(
            xyz,
            np.array([0.0, 1.0, 0.0]),
            0.0,
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
            pad_m=0.05,
            minimum_support=2,
        )
        self.assertEqual(floor["bounds_u_m"], [-1.05, 1.05])
        self.assertEqual(floor["bounds_v_m"], [1.95, 4.05])
        self.assertEqual(floor["support_points_20mm"], 2)
        self.assertTrue(floor["certified_for_generation"])

    def test_bilinear_rgb(self):
        image = np.array(
            [
                [[0, 0, 0], [10, 20, 30]],
                [[20, 40, 60], [30, 60, 90]],
            ],
            dtype=np.uint8,
        )
        sampled = MODULE.bilinear_rgb(image, np.array([[0.5, 0.5]]))
        self.assertTrue(np.allclose(sampled[0], [15, 30, 45]))

    def test_unique_depth_winner_requires_ncc_margin(self):
        unique, observed = MODULE.unique_depth_winner(4, 0.91, [(4, 0.90)], 0.02)
        self.assertFalse(unique)
        self.assertAlmostEqual(observed, 0.01)

    def test_unique_depth_winner_accepts_clear_peak(self):
        unique, observed = MODULE.unique_depth_winner(
            5, 0.93, [(5, 0.88), (4, 0.89)], 0.02
        )
        self.assertTrue(unique)
        self.assertAlmostEqual(observed, 0.04)

    def test_unique_depth_winner_rejects_more_supported_alternative(self):
        unique, _ = MODULE.unique_depth_winner(4, 0.95, [(5, 0.90)], 0.02)
        self.assertFalse(unique)

    def test_each_point_ranks_its_own_most_head_on_views(self):
        visible = np.array([True, False, True, True, True])
        head_on = np.array([0.5, 1.0, 0.9, 0.7, 0.9])
        selected = MODULE.select_point_views(visible, head_on, 3)
        self.assertEqual(selected, [2, 4, 3])

    def test_structural_tile_views_prioritize_coverage_then_incidence(self):
        visible = np.array(
            [
                [True, True, True, False],
                [True, True, False, False],
                [True, True, True, False],
                [False, False, False, False],
            ]
        )
        head_on = np.array(
            [
                [0.6, 0.6, 0.6, 0.0],
                [1.0, 1.0, 0.0, 0.0],
                [0.8, 0.8, 0.8, 0.0],
                [1.0, 1.0, 1.0, 1.0],
            ]
        )
        selected = MODULE.select_tile_views(visible, head_on, 3)
        self.assertEqual(selected, [2, 0, 1])

    def test_structural_tile_view_ties_are_deterministic(self):
        visible = np.ones((3, 2), dtype=bool)
        head_on = np.full((3, 2), 0.75)
        self.assertEqual(MODULE.select_tile_views(visible, head_on, 2), [0, 1])

    def test_scale_rescue_keeps_baseline_order_and_only_appends_new_points(self):
        baseline_xyz = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        baseline_rgb = np.array([[10.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
        baseline_meta = np.array([[4.0, 10.0, 0.8, 4.0], [5.0, 12.0, 0.9, 5.0]])
        rescue_xyz = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        rescue_rgb = np.array([[99.0, 0.0, 0.0], [30.0, 0.0, 0.0]])
        rescue_meta = np.array([[6.0, 15.0, 0.95, 6.0], [4.0, 11.0, 0.85, 4.0]])
        xyz, rgb, meta, added = MODULE.merge_scale_rescue_results(
            baseline_xyz,
            baseline_rgb,
            baseline_meta,
            rescue_xyz,
            rescue_rgb,
            rescue_meta,
        )
        self.assertEqual(added, 1)
        self.assertEqual(xyz.tolist(), [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        self.assertEqual(rgb[:, 0].tolist(), [10.0, 20.0, 30.0])
        self.assertEqual(meta[:, 2].tolist(), [0.8, 0.9, 0.85])

    def test_scale_rescue_quality_gate_requires_every_strict_threshold(self):
        metadata = np.array(
            [
                [5.0, 18.0, 0.90, 6.0],
                [4.0, 20.0, 0.95, 6.0],
                [6.0, 17.9, 0.95, 6.0],
                [6.0, 20.0, 0.899, 6.0],
            ]
        )
        mask = MODULE.scale_rescue_quality_mask(metadata, 5, 18.0, 0.90)
        self.assertEqual(mask.tolist(), [True, False, False, False])

    def test_rescue_gate_requires_all_baseline_medians(self):
        evidence = {"views": 4, "ncc": 0.85, "parallax": 10.0}
        self.assertTrue(MODULE.passes_rescue_gate(evidence, 0.84, 9.0, 3))
        self.assertFalse(MODULE.passes_rescue_gate(evidence, 0.86, 9.0, 3))
        self.assertFalse(MODULE.passes_rescue_gate(evidence, 0.84, 11.0, 3))
        self.assertFalse(MODULE.passes_rescue_gate(evidence, 0.84, 9.0, 5))


if __name__ == "__main__":
    unittest.main()
