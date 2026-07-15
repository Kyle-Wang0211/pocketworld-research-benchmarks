#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("generate_fixture.py")


def load_generator():
    spec = importlib.util.spec_from_file_location("plane_sweep_a16_fixture", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerateFixtureTest(unittest.TestCase):
    def test_fixture_uses_accepted_floor_owner_rescue_contract(self):
        module = load_generator()
        contract = module.fixture_contract()

        self.assertEqual(contract["surface_id"], "floor_0")
        self.assertEqual(contract["tile_index"], 47)
        self.assertEqual(contract["tile_points"], 64)
        self.assertEqual(contract["grid_m"], 0.05)
        self.assertEqual(contract["base_max_views"], 10)
        self.assertEqual(contract["max_views"], 48)
        self.assertEqual(contract["min_views"], 3)
        self.assertEqual(contract["ncc_min"], 0.70)
        self.assertEqual(contract["min_parallax_deg"], 5.0)
        self.assertAlmostEqual(contract["rescue_min_ncc"], 0.8500471980155323)
        self.assertAlmostEqual(
            contract["rescue_min_parallax_deg"], 10.241134230890212
        )
        self.assertEqual(contract["rescue_min_views"], 3)
        self.assertEqual(contract["depth_competition_offsets_m"], ())
        self.assertTrue(str(module.PLANES).endswith("structural_planes_v5_floor.json"))

    def test_resource_view_indices_preserve_each_points_candidate_order(self):
        module = load_generator()
        per_point_global = [[8, 3, 5], [3, 9], []]

        union, per_point_resource = module.map_point_view_indices(per_point_global)

        self.assertEqual(union, [3, 5, 8, 9])
        self.assertEqual(per_point_resource, [[2, 0, 1], [0, 3], []])


if __name__ == "__main__":
    unittest.main()
