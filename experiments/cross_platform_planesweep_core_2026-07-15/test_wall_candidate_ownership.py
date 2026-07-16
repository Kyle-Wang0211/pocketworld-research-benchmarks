#!/usr/bin/env python3
from __future__ import annotations

import unittest

import select_wall_plane_candidates as selector


def surface(identifier: str, theta: float, value: float, incumbent: bool) -> dict:
    return {
        "surface_id": identifier,
        "theta_deg_in_horizontal_basis": theta,
        "plane_value_n_dot_x": value,
        "score": 1.0,
        "candidate_source_certified_for_generation": incumbent,
    }


class WallCandidateOwnershipTest(unittest.TestCase):
    def test_two_incumbents_never_collapse_into_one_family(self) -> None:
        surfaces = [
            surface("old_a", 60.0, 1.00, True),
            surface("old_b", 65.0, 1.40, True),
            surface("new", 63.0, 1.20, False),
        ]
        families = selector.competing_families(surfaces)
        self.assertEqual(len(families), 2)
        self.assertEqual(sum(0 in family for family in families), 1)
        self.assertEqual(sum(1 in family for family in families), 1)

    def test_open_family_still_uses_fixed_representative(self) -> None:
        surfaces = [
            surface("a", 55.0, -2.48, False),
            surface("b", 60.0, -2.52, False),
            surface("c", 120.0, 1.00, False),
        ]
        families = selector.competing_families(surfaces)
        self.assertEqual(sorted(map(len, families)), [1, 2])

    def test_birth_minimum_is_joint_point_and_coverage_gate(self) -> None:
        row = {
            "metrics": {"accepted": 8, "coverage_cells_5cm": 7},
            "winner_score": 8.0,
        }
        self.assertFalse(selector.passes_birth_minimum(row))
        row["metrics"]["coverage_cells_5cm"] = 8
        self.assertTrue(selector.passes_birth_minimum(row))


if __name__ == "__main__":
    unittest.main()
