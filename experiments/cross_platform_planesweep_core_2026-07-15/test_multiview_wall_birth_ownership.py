#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from apply_multiview_wall_birth_ownership import (
    PointEvidence,
    greedy_birth_owner,
    layer_geometry,
    read_ascii_ply,
    remaining_conflicts,
)


def point(index: int, *, nviews: float, zncc: float, xyz=(0.0, 0.0, 0.0)) -> PointEvidence:
    return PointEvidence(
        index=index,
        surface_id=f"wall_{index}",
        xyz=np.asarray(xyz, dtype=np.float64),
        normal=np.asarray([1.0, 0.0, 0.0]),
        nviews=nviews,
        parallax_deg=10.0,
        zncc_median=zncc,
    )


class MultiviewWallBirthOwnershipTest(unittest.TestCase):
    def test_greedy_owner_keeps_stronger_and_clears_conflict(self) -> None:
        points = [point(0, nviews=4, zncc=0.91), point(1, nviews=7, zncc=0.90)]
        conflicts = {(0, 1): {"frame_ids": [3, 8]}}
        published, withheld = greedy_birth_owner(points, conflicts)
        self.assertEqual(published, [1])
        self.assertEqual(withheld[0]["point_index"], 0)
        self.assertEqual(withheld[0]["owner_point_index"], 1)
        self.assertEqual(remaining_conflicts(conflicts, published), 0)

    def test_layer_geometry_distinguishes_parallel_layer_from_tangent_neighbor(self) -> None:
        first = point(0, nviews=5, zncc=0.9, xyz=(0.0, 0.0, 0.0))
        normal_layer = point(1, nviews=5, zncc=0.9, xyz=(0.05, 0.0, 0.0))
        tangent_neighbor = point(2, nviews=5, zncc=0.9, xyz=(0.0, 0.05, 0.0))
        self.assertAlmostEqual(layer_geometry(first, normal_layer)["normal_separation_mm"], 50.0)
        self.assertAlmostEqual(layer_geometry(first, normal_layer)["tangent_separation_mm"], 0.0)
        self.assertAlmostEqual(layer_geometry(first, tangent_neighbor)["normal_separation_mm"], 0.0)
        self.assertAlmostEqual(layer_geometry(first, tangent_neighbor)["tangent_separation_mm"], 50.0)

    def test_ascii_ply_requires_exact_vertex_payload(self) -> None:
        body = """ply
format ascii 1.0
element vertex 1
property float x
property float y
property float z
property float nviews
property float parallax_deg
property float zncc_median
end_header
1 2 3 4 5 0.9
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "point.ply"
            path.write_text(body)
            parsed = read_ascii_ply(path)
        self.assertEqual(parsed["x"].tolist(), [1.0])
        self.assertEqual(parsed["zncc_median"].tolist(), [0.9])


if __name__ == "__main__":
    unittest.main()
