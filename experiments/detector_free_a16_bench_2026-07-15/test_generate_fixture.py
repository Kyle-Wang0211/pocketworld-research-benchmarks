import importlib.util
import sys
import unittest
import struct
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("generate_fixture.py")
SPEC = importlib.util.spec_from_file_location("detector_free_a16_fixture", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FixtureContractTest(unittest.TestCase):
    def test_contract_is_model_free_and_bounded_for_a16(self):
        contract = MODULE.fixture_contract()
        self.assertEqual((contract["width"], contract["height"]), (128, 72))
        self.assertEqual(contract["depth_samples"], 48)
        self.assertEqual(contract["source_count"], 7)
        self.assertEqual(contract["patch_n"], 5)
        self.assertEqual(contract["min_views"], 4)
        self.assertFalse(contract["learned_model_consumed"])
        self.assertFalse(contract["lidar_or_scene_depth_consumed"])

    def test_reference_to_source_projection_matches_world_projection(self):
        geometry = MODULE.load_geometry_module()
        depth = MODULE.load_depth_module()
        frames = depth.load_sidecar_frames(
            geometry, depth.CAP56_LEDGER, depth.CAP56_PHOTOS
        )
        reference = frames[10]
        source = frames[3]
        projection = MODULE.reference_camera_projection(reference, source, 128, 72)
        reference_point = np.asarray([0.08, -0.04, 1.7, 1.0])
        direct = projection @ reference_point

        world = (reference_point[:3] - reference.t) @ reference.R
        source_camera = world @ source.R.T + source.t
        source_k = depth.scaled_intrinsics(source, 128, 72)
        expected = source_k @ source_camera

        np.testing.assert_allclose(direct, expected, rtol=1e-11, atol=1e-11)

    def test_registered_parity_keeps_product_births_and_depths_exact(self):
        thresholds = MODULE.registered_thresholds()
        self.assertEqual(thresholds["accepted_mismatch_max"], 0)
        self.assertEqual(thresholds["accepted_best_index_mismatch_max"], 0)
        self.assertEqual(thresholds["views_mismatch_max"], 0)
        self.assertEqual(
            thresholds["all_valid_best_index_mismatch"],
            "diagnostic_only_for_rejected_candidates",
        )

    def test_reference_index_is_explicit_fixture_identity(self):
        self.assertEqual(MODULE.fixture_contract(17)["reference_index"], 17)

    def test_portable_params_abi_is_112_bytes(self):
        self.assertEqual(struct.calcsize("<8I20f"), 112)


if __name__ == "__main__":
    unittest.main()
