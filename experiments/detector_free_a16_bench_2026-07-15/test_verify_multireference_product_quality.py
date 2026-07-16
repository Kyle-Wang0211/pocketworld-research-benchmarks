import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np


MODULE_PATH = Path(__file__).with_name("verify_multireference_product_quality.py")
SPEC = importlib.util.spec_from_file_location(
    "detector_free_multireference_product_quality", MODULE_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SkipInsufficientSupportContractTest(unittest.TestCase):
    def run_main(self, evaluation_results, *, skip=True, references=(7,)):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            library = temporary / "libaether3d_ffi.dylib"
            sparse = temporary / "sparse.npz"
            output = temporary / "result.json"
            output_dir = temporary / "references"
            library.write_bytes(b"library fixture")
            sparse.write_bytes(b"sparse fixture")
            depth = SimpleNamespace(
                capture_bundle_sha256=lambda _frames: "ordered-capture-hash"
            )
            argv = [
                str(MODULE_PATH),
                "--library",
                str(library),
                "--capture",
                "cap40",
                "--output-dir",
                str(output_dir),
                "--output",
                str(output),
            ]
            for reference in references:
                argv.extend(("--reference-index", str(reference)))
            if skip:
                argv.append("--skip-insufficient-support")

            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(MODULE, "load_module", return_value=depth),
                mock.patch.object(MODULE, "load_api", return_value=object()),
                mock.patch.object(
                    MODULE,
                    "load_capture",
                    return_value=([object()], sparse, None),
                ),
                mock.patch.object(
                    MODULE,
                    "read_sparse_xyz",
                    return_value=np.empty((0, 3), dtype=np.float64),
                ),
                mock.patch.object(
                    MODULE,
                    "evaluate_reference",
                    side_effect=evaluation_results,
                ),
            ):
                return_code = MODULE.main()

            return return_code, json.loads(output.read_text())

    def test_both_explicit_insufficient_support_errors_are_zero_birth_noops(self):
        return_code, result = self.run_main(
            [
                ValueError("only 2 independent supports for frame 7; need 4"),
                ValueError("fewer than four overlap sources for frame 9"),
            ],
            references=(7, 9),
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(result["requested_reference_count"], 2)
        self.assertEqual(result["evaluated_reference_count"], 0)
        self.assertEqual(
            result["skipped_references"],
            [
                {
                    "births": 0,
                    "reason": "only 2 independent supports for frame 7; need 4",
                    "reference_index": 7,
                },
                {
                    "births": 0,
                    "reason": "fewer than four overlap sources for frame 9",
                    "reference_index": 9,
                },
            ],
        )
        self.assertEqual(result["totals"]["baseline_births"], 0)
        self.assertEqual(result["totals"]["reciprocal_births"], 0)
        self.assertEqual(result["totals"]["final_births"], 0)
        self.assertEqual(result["totals"]["depth_conflict_candidates"], 0)
        self.assertEqual(
            result["decision"], "FAIL_RECIPROCAL_BIRTH_QUALITY_GATE"
        )

    def test_unrelated_value_error_is_never_swallowed(self):
        with self.assertRaisesRegex(ValueError, "invalid metric sparse XYZ"):
            self.run_main([ValueError("invalid metric sparse XYZ: corrupt.npz")])

    def test_known_support_error_still_aborts_without_opt_in(self):
        with self.assertRaisesRegex(ValueError, "independent supports"):
            self.run_main(
                [ValueError("only 3 independent supports for frame 7; need 4")],
                skip=False,
            )

    def test_skips_do_not_inflate_counts_or_satisfy_decision_preconditions(self):
        accepted_reference = {
            "pass": True,
            "baseline_births": 11,
            "reciprocal_births": 5,
            "final_births": 5,
            "depth_conflict_candidates": 6,
            "depth_conflict_candidates_born": 0,
            "floor_owned_candidates_not_born": 2,
        }
        return_code, result = self.run_main(
            [
                ValueError("only 1 independent supports for frame 7; need 4"),
                accepted_reference,
            ],
            references=(7, 9),
        )

        self.assertEqual(return_code, 0)
        self.assertEqual(result["evaluated_reference_count"], 1)
        self.assertEqual(len(result["skipped_references"]), 1)
        self.assertEqual(result["skipped_references"][0]["births"], 0)
        self.assertEqual(result["totals"]["baseline_births"], 11)
        self.assertEqual(result["totals"]["reciprocal_births"], 5)
        self.assertEqual(result["totals"]["final_births"], 5)
        self.assertEqual(result["totals"]["depth_conflict_candidates"], 6)
        self.assertEqual(
            result["decision"],
            "PASS_ADDITIVE_RECIPROCAL_BIRTH_ZERO_REGRESSION",
        )


if __name__ == "__main__":
    unittest.main()
