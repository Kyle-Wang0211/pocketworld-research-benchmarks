#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("evaluate_local_manifold_birth_gate.py")
SPEC = importlib.util.spec_from_file_location("birth_gate_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
birth_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = birth_gate
SPEC.loader.exec_module(birth_gate)


class ReferenceCertificateTest(unittest.TestCase):
    def test_default_preserves_old_product_gate(self):
        gate = np.asarray([True, False, True], dtype=bool)
        folds = [{"non_regression": True}, {"non_regression": False}]
        actual, certified, blocked = birth_gate.apply_reference_certificate(
            gate, folds, required=False
        )
        np.testing.assert_array_equal(actual, gate)
        self.assertFalse(certified)
        self.assertEqual(blocked, 0)

    def test_required_certificate_blocks_entire_reference_before_birth(self):
        gate = np.asarray([True, False, True], dtype=bool)
        folds = [
            {"non_regression": True},
            {"non_regression": False},
            {"non_regression": True},
        ]
        actual, certified, blocked = birth_gate.apply_reference_certificate(
            gate, folds, required=True
        )
        np.testing.assert_array_equal(actual, np.zeros(3, dtype=bool))
        self.assertFalse(certified)
        self.assertEqual(blocked, 2)

    def test_certified_reference_keeps_births(self):
        gate = np.asarray([True, False, True], dtype=bool)
        folds = [{"non_regression": True} for _ in range(3)]
        actual, certified, blocked = birth_gate.apply_reference_certificate(
            gate, folds, required=True
        )
        np.testing.assert_array_equal(actual, gate)
        self.assertTrue(certified)
        self.assertEqual(blocked, 0)

    def test_zero_birth_certified_mode_passes(self):
        self.assertTrue(
            birth_gate.gate_passed(
                all_non_regression=False,
                total_product_births=0,
                c_abi_required_pass=True,
                require_reference_certificate=True,
                all_uncertified_references_blocked=True,
            )
        )

    def test_uncertified_birth_or_c_abi_failure_fails(self):
        common = dict(
            all_non_regression=False,
            total_product_births=0,
            require_reference_certificate=True,
        )
        self.assertFalse(
            birth_gate.gate_passed(
                **common,
                c_abi_required_pass=True,
                all_uncertified_references_blocked=False,
            )
        )
        self.assertFalse(
            birth_gate.gate_passed(
                **common,
                c_abi_required_pass=False,
                all_uncertified_references_blocked=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
