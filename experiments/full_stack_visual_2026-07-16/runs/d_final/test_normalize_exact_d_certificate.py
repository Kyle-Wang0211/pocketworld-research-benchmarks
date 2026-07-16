#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SUBJECT_PATH = Path(__file__).with_name("normalize_exact_d_certificate.py")
SPEC = importlib.util.spec_from_file_location("normalize_exact_d_certificate", SUBJECT_PATH)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class NormalizeExactDCertificateTest(unittest.TestCase):
    def test_fail_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed PASS"):
            subject.validate_source_status({"status": "FAIL_REFERENCE_CERTIFICATE"})

    def test_conflicting_model_or_loftr_flags_are_rejected(self) -> None:
        execution = {"immutable_inputs": {"jpeg_backend_label": "libjpeg_turbo_product"}}
        with self.assertRaisesRegex(ValueError, "model_weights_consumed"):
            subject.validate_commercial_clean_source(
                {"commercial_clean": {**subject.COMMERCIAL_CLEAN, "model_weights_consumed": True}},
                execution,
                [],
            )
        with self.assertRaisesRegex(ValueError, "loftr_consumed"):
            subject.validate_commercial_clean_source(
                {"commercial_clean": {**subject.COMMERCIAL_CLEAN, "loftr_consumed": True}},
                execution,
                [],
            )

    def test_tampered_available_asset_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "frame.jpg"
            path.write_bytes(b"actual")
            inventory = {
                "total_count": 1,
                "available_count": 1,
                "available_inputs": [{"id": "7", "path": str(path), "sha256": "0" * 64}],
                "missing_inputs": [],
                "coverage_fraction": 1.0,
            }
            with self.assertRaisesRegex(ValueError, "identity/hash"):
                subject.validate_inventory(inventory, {"missing_registered_jpeg_frame_ids": []})

    def test_output_count_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "output count"):
            subject.validate_output_counts({"final_births": 8}, 8, 7)
        with self.assertRaisesRegex(ValueError, "output count"):
            subject.validate_output_counts({"final_births": 9}, 8, 8)


if __name__ == "__main__":
    unittest.main()
