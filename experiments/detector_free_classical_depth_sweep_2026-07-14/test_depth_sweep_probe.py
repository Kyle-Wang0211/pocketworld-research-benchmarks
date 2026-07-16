from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("depth_sweep_probe.py")
SPEC = importlib.util.spec_from_file_location("depth_sweep_probe_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class QuadraticPeakRefinementTest(unittest.TestCase):
    def test_recovers_subsample_peak_in_inverse_depth_coordinate(self) -> None:
        # Samples of -(x - 0.25)^2 at x=-1, 0, 1 have their discrete maximum
        # at x=0 while the exact quadratic maximum is one quarter sample right.
        costs = np.asarray([-0.625, -0.025, -0.225], dtype=np.float32).reshape(3, 1, 1)
        best = np.asarray([[1]], dtype=np.int64)

        offsets = MODULE.quadratic_peak_offsets(costs, best)

        self.assertAlmostEqual(float(offsets[0, 0]), 0.25, places=6)

    def test_leaves_boundary_and_non_concave_peaks_unmodified(self) -> None:
        costs = np.asarray(
            [
                [[3.0, 0.0]],
                [[2.0, 1.0]],
                [[1.0, 2.0]],
            ],
            dtype=np.float32,
        )
        best = np.asarray([[0, 1]], dtype=np.int64)

        offsets = MODULE.quadratic_peak_offsets(costs, best)

        np.testing.assert_array_equal(offsets, np.zeros((1, 2), dtype=np.float32))

    def test_safe_gate_only_refines_supported_mid_offset_near_depth_peaks(self) -> None:
        offsets = np.asarray(
            [[0.1999, 0.20, -0.2999, 0.30, 0.25, 0.25]], dtype=np.float32
        )
        depths = np.asarray(
            [[1.0, 1.0, 1.49, 1.0, 1.50, 1.0]], dtype=np.float32
        )
        scores = np.asarray(
            [[0.80, 0.80, 0.9249, 0.80, 0.80, 0.925]], dtype=np.float32
        )

        mask = MODULE.safe_quadratic_refinement_mask(offsets, depths, scores)

        np.testing.assert_array_equal(
            mask,
            np.asarray([[False, True, True, False, False, False]]),
        )

    def test_conservative_gate_requires_weak_but_unambiguous_near_peak(self) -> None:
        offsets = np.asarray(
            [[0.1499, 0.15, -0.3999, 0.40, 0.20, 0.20, 0.20]], dtype=np.float32
        )
        depths = np.asarray(
            [[1.0, 1.0, 1.49, 1.0, 1.50, 1.0, 1.0]], dtype=np.float32
        )
        scores = np.asarray(
            [[0.70, 0.70, 0.7999, 0.70, 0.70, 0.80, 0.70]], dtype=np.float32
        )
        margins = np.asarray(
            [[0.10, 0.10, 0.1499, 0.10, 0.10, 0.10, 0.15]], dtype=np.float32
        )

        mask = MODULE.conservative_quadratic_refinement_mask(
            offsets, depths, scores, margins
        )

        np.testing.assert_array_equal(
            mask,
            np.asarray([[False, True, True, False, False, False, False]]),
        )


class SidecarCaptureLoaderTest(unittest.TestCase):
    def test_loads_all_cap56_frames_with_per_frame_intrinsics(self) -> None:
        geometry = MODULE.load_geometry_module()

        frames = MODULE.load_sidecar_frames(
            geometry,
            MODULE.CAP56_LEDGER,
            MODULE.CAP56_PHOTOS,
        )

        self.assertEqual([frame.frame_id for frame in frames], list(range(20)))
        self.assertTrue(all(frame.width == 3840 for frame in frames))
        self.assertTrue(all(frame.height == 2160 for frame in frames))
        self.assertGreater(float(np.ptp([frame.K[0, 0] for frame in frames])), 20.0)
        self.assertEqual(len({frame.image_path.name for frame in frames}), 20)

    def test_automatic_source_selection_is_bounded_and_deterministic(self) -> None:
        geometry = MODULE.load_geometry_module()
        frames = MODULE.load_sidecar_frames(
            geometry,
            MODULE.CAP56_LEDGER,
            MODULE.CAP56_PHOTOS,
        )

        first = MODULE.select_source_indices(frames, reference_index=10, count=7)
        second = MODULE.select_source_indices(frames, reference_index=10, count=7)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 7)
        self.assertNotIn(10, first)
        for index in first:
            baseline = np.linalg.norm(frames[index].C - frames[10].C)
            self.assertGreaterEqual(float(baseline), 0.08)
            self.assertLessEqual(float(baseline), 0.75)


if __name__ == "__main__":
    unittest.main()
