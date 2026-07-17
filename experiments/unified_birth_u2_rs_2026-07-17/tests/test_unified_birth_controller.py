from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from unified_birth_controller import (  # noqa: E402
    decide_birth,
    publish_directory_no_replace,
    read_ply,
    validate_evidence_row,
    validate_output_layout,
)


class DecideBirthTest(unittest.TestCase):
    def test_defers_only_when_reliable_conflicts_outvote_agreements(self) -> None:
        self.assertEqual(decide_birth(agreement=0, free_space_conflict=1), "DEFERRED")
        self.assertEqual(decide_birth(agreement=1, free_space_conflict=2), "DEFERRED")

    def test_certifies_ties_and_positive_surface_consensus(self) -> None:
        self.assertEqual(decide_birth(agreement=0, free_space_conflict=0), "CERTIFIED")
        self.assertEqual(decide_birth(agreement=1, free_space_conflict=1), "CERTIFIED")
        self.assertEqual(decide_birth(agreement=3, free_space_conflict=1), "CERTIFIED")

    def test_rejects_invalid_counts(self) -> None:
        with self.assertRaises(ValueError):
            decide_birth(agreement=-1, free_space_conflict=0)

    def test_rejects_conflict_omitted_from_claimed_aggregate(self) -> None:
        evidence = {
            "class_counts": {
                "ABSTAIN": 0,
                "AGREEMENT": 0,
                "FREE_SPACE_CONFLICT": 0,
                "OCCLUDED_ABSTAIN": 0,
            },
            "source_evidence": [
                {"classification": "FREE_SPACE_CONFLICT"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "exact aggregate mismatch"):
            validate_evidence_row(evidence, row_index=0)

    def test_rejects_unknown_evidence_classification(self) -> None:
        evidence = {
            "class_counts": {
                "ABSTAIN": 1,
                "AGREEMENT": 0,
                "FREE_SPACE_CONFLICT": 0,
                "OCCLUDED_ABSTAIN": 0,
            },
            "source_evidence": [{"classification": "UNKNOWN"}],
        }
        with self.assertRaisesRegex(ValueError, "unknown classification"):
            validate_evidence_row(evidence, row_index=0)

    def test_rejects_existing_output_directory_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            source.write_bytes(b"immutable")
            output = root / "output"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                validate_output_layout((source,), output)
            self.assertEqual(source.read_bytes(), b"immutable")

    def test_rejects_non_xyzrgb_ply_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "wrong.ply"
            path.write_bytes(
                b"ply\n"
                b"format binary_little_endian 1.0\n"
                b"element vertex 1\n"
                b"property int x\n"
                b"property float y\n"
                b"property float z\n"
                b"property uchar red\n"
                b"property uchar green\n"
                b"property uchar blue\n"
                b"end_header\n"
                + bytes(15)
            )
            with self.assertRaisesRegex(ValueError, "exact packed xyzrgb"):
                read_ply(path)

    @unittest.skipUnless(sys.platform == "darwin", "requires renameatx_np")
    def test_atomic_publish_never_replaces_existing_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            staging.mkdir()
            (staging / "candidate_full.ply").write_bytes(b"candidate")
            output = root / "output"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                publish_directory_no_replace(staging, output)
            self.assertTrue(staging.is_dir())
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
