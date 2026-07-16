import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("evaluate_refinement_ab.py")
SPEC = importlib.util.spec_from_file_location("evaluate_refinement_ab", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_run(path: Path, depth: np.ndarray, accepted: np.ndarray, truth: np.ndarray):
    path.mkdir(parents=True)
    np.savez_compressed(
        path / "depth_sweep.npz",
        depth_m=depth.astype(np.float32),
        discrete_depth_m=np.ones_like(depth, dtype=np.float32),
        accepted=accepted.astype(bool),
        best_ncc=np.full_like(depth, 0.9, dtype=np.float32),
        second_ncc=np.full_like(depth, 0.8, dtype=np.float32),
        views=np.full_like(depth, 4, dtype=np.uint8),
        consistency_views=np.full_like(depth, 4, dtype=np.uint8),
        sparse_depth_eval_m=truth.astype(np.float32),
    )
    (path / "metrics.json").write_text(
        json.dumps({"metrics": {"accepted_pixels": int(accepted.sum())}}) + "\n"
    )


class RefinementABTest(unittest.TestCase):
    def test_pass_requires_identical_birth_and_no_per_pixel_regression(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = np.array([[True, True]])
            truth = np.array([[1.0, 2.0]])
            write_run(root / "ref0" / "off", np.array([[0.9, 2.2]]), accepted, truth)
            write_run(root / "ref0" / "on", np.array([[0.95, 2.1]]), accepted, truth)

            verdict = MODULE.evaluate_runs(root, "off", "on")

            self.assertEqual(verdict["verdict"], "PASS_ZERO_REGRESSION")
            self.assertEqual(verdict["totals"]["improved_pixels"], 2)
            self.assertEqual(verdict["totals"]["regressed_pixels"], 0)

    def test_single_worse_pixel_fails_even_when_mean_improves(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = np.array([[True, True]])
            truth = np.array([[1.0, 2.0]])
            write_run(root / "ref0" / "off", np.array([[0.5, 2.2]]), accepted, truth)
            write_run(root / "ref0" / "on", np.array([[0.9, 2.3]]), accepted, truth)

            verdict = MODULE.evaluate_runs(root, "off", "on")

            self.assertEqual(verdict["verdict"], "FAIL_REGRESSION")
            self.assertEqual(verdict["totals"]["improved_pixels"], 1)
            self.assertEqual(verdict["totals"]["regressed_pixels"], 1)

    def test_birth_mask_change_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            truth = np.array([[1.0, 2.0]])
            write_run(
                root / "ref0" / "off",
                np.array([[1.0, 2.0]]),
                np.array([[True, False]]),
                truth,
            )
            write_run(
                root / "ref0" / "on",
                np.array([[1.0, 2.0]]),
                np.array([[True, True]]),
                truth,
            )

            verdict = MODULE.evaluate_runs(root, "off", "on")

            self.assertEqual(verdict["verdict"], "FAIL_BIRTH_OR_INPUT_IDENTITY")
            self.assertFalse(verdict["references"][0]["birth_identity"]["accepted"])


if __name__ == "__main__":
    unittest.main()
