import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("generate_wall_scale_rescue_fixture.py")
SPEC = importlib.util.spec_from_file_location("generate_wall_scale_rescue_fixture", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class WallScaleRescueFixtureTest(unittest.TestCase):
    def test_contract_keeps_baseline_and_strengthens_rescue(self):
        baseline = MODULE.base_contract()
        rescue = MODULE.rescue_contract()
        self.assertEqual(baseline["patch_radius_m"], 0.03)
        self.assertEqual(rescue["patch_radius_m"], 0.06)
        self.assertGreater(rescue["min_views"], baseline["min_views"])
        self.assertGreater(rescue["min_parallax_deg"], baseline["min_parallax_deg"])
        self.assertGreater(rescue["depth_ncc_margin"], baseline["depth_ncc_margin"])
        self.assertEqual(rescue["post_min_ncc"], 0.90)

    def test_rgba_packing_is_little_endian_and_lossless(self):
        rgb = np.array([[[1, 2, 3], [254, 128, 64]]], dtype=np.uint8)
        packed = MODULE.pack_rgba8(rgb)
        self.assertEqual(int(packed[0, 0]), 0xFF030201)
        self.assertEqual(int(packed[0, 1]), 0xFF4080FE)


if __name__ == "__main__":
    unittest.main()
