from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PYTHON_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_TOOLS))

import b0_input_contract as contract


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _minimal_contract(
    *,
    dataset_id: str = "synthetic_metric",
    frames: list[str] | None = None,
) -> dict[str, object]:
    frames = frames or ["rec_0.jpg", "held_0.jpg"]
    model_frames = list(reversed(frames))
    image_identities = {
        name: {"sha256": _sha256(name.encode("utf-8")), "size_bytes": index + 10}
        for index, name in enumerate(frames)
    }
    reconstruction = [frames[0]]
    heldout = [frames[1]]
    return {
        "schema_version": "b0-input-contract-v1",
        "dataset_id": dataset_id,
        "coordinate_frame": "metric_arkit_cv",
        "metres_per_model_unit": 1.0,
        "transductive_policy": {
            "present": False,
            "route_allowed": True,
            "quality_scoring_forbidden": False,
        },
        "dmcache": {
            "sha256": "1" * 64,
            "signature": "synthetic-camera-z",
            "depth": {"shape": [2, 512, 896], "dtype": "float32"},
            "frame_order": frames,
            "frame_order_sha256": contract.ordered_frame_names_sha256(frames),
        },
        "model_cache": {
            "sha256": "2" * 64,
            "frame_order": model_frames,
            "frame_order_sha256": contract.ordered_frame_names_sha256(model_frames),
        },
        "splits": {
            "quality": {
                "reconstruction": {
                    "frames": reconstruction,
                    "file_sha256": contract.ordered_frame_names_sha256(reconstruction),
                    "semantic_sha256": contract.ordered_frame_names_sha256(reconstruction),
                },
                "heldout": {
                    "frames": heldout,
                    "file_sha256": contract.ordered_frame_names_sha256(heldout),
                    "semantic_sha256": contract.ordered_frame_names_sha256(heldout),
                },
            }
        },
        "images": {
            "root_manifest_sha256": contract.image_identity_manifest_sha256(
                frames, image_identities
            ),
            "by_name": image_identities,
        },
    }


class FrameListContractTests(unittest.TestCase):
    def test_parses_json_object_and_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.json"
            path.write_text(
                json.dumps({"reconstruction_frames": ["a.jpg", "c.jpg"]}),
                encoding="utf-8",
            )
            self.assertEqual(contract.parse_frame_list(path), ["a.jpg", "c.jpg"])

    def test_arbitrary_frozen_order_is_preserved(self) -> None:
        self.assertEqual(
            contract.validate_ordered_subsequence(
                ["c.jpg", "a.jpg"], ["a.jpg", "b.jpg", "c.jpg"]
            ),
            [2, 0],
        )

    def test_text_frame_names_are_not_silently_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.txt"
            path.write_text("a.jpg\n b.jpg\n", encoding="utf-8")
            with self.assertRaisesRegex(
                contract.RouteInputNotEquivalent,
                r"^ROUTE_INPUT_NOT_EQUIVALENT$",
            ):
                contract.parse_frame_list(path)

    def test_rejects_duplicate_or_missing_frames_fail_closed(self) -> None:
        for requested in (["a.jpg", "a.jpg"], ["missing.jpg"]):
            with self.subTest(requested=requested):
                with self.assertRaisesRegex(
                    contract.RouteInputNotEquivalent,
                    r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                ):
                    contract.validate_ordered_subsequence(
                        requested, ["a.jpg", "b.jpg", "c.jpg"]
                    )


class HashContractTests(unittest.TestCase):
    def test_stream_and_file_sha256_are_identical(self) -> None:
        payload = b"camera-z-depth\x00" * 31
        expected = hashlib.sha256(payload).hexdigest()
        self.assertEqual(contract.sha256_stream(io.BytesIO(payload), chunk_size=7), expected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.bin"
            path.write_bytes(payload)
            self.assertEqual(contract.sha256_file(path, chunk_size=11), expected)

    def test_semantic_hash_changes_for_any_route_input(self) -> None:
        depth = np.array([[1.0, 2.0], [0.0, 3.0]], dtype=np.float32)
        mask = depth > 0
        K = np.array([[10.0, 0.0, 0.5], [0.0, 11.0, 0.5], [0.0, 0.0, 1.0]], dtype=np.float32)
        w2c = np.eye(4, dtype=np.float32)
        base = contract.canonical_frame_semantic_sha256("a.jpg", mask, depth, K, w2c)
        changed_depth = depth.copy()
        changed_depth[0, 0] += np.float32(0.125)
        changed_mask = mask.copy()
        changed_mask[0, 0] = False
        changed_K = K.copy()
        changed_K[0, 0] += np.float32(0.25)
        changed_w2c = w2c.copy()
        changed_w2c[0, 3] += np.float32(0.5)
        variants = [
            contract.canonical_frame_semantic_sha256(
                "b.jpg", mask, depth, K, w2c
            ),
            contract.canonical_frame_semantic_sha256(
                "a.jpg", changed_mask, depth, K, w2c
            ),
            contract.canonical_frame_semantic_sha256(
                "a.jpg", mask, changed_depth, K, w2c
            ),
            contract.canonical_frame_semantic_sha256(
                "a.jpg", mask, depth, changed_K, w2c
            ),
            contract.canonical_frame_semantic_sha256(
                "a.jpg", mask, depth, K, changed_w2c
            ),
        ]
        for other in variants:
            self.assertNotEqual(base, other)
        with self.assertRaisesRegex(
            contract.RouteInputNotEquivalent,
            r"^ROUTE_INPUT_NOT_EQUIVALENT$",
        ):
            contract.assert_semantic_hashes_equal([base], [variants[0]])

    def test_common_contract_hash_encodings_are_exact(self) -> None:
        frames = ["z_tap-02.jpg", "a_tap-01.jpg"]
        identities = {
            "z_tap-02.jpg": {"sha256": "a" * 64, "size_bytes": 7},
            "a_tap-01.jpg": {"sha256": "b" * 64, "size_bytes": 11},
        }
        self.assertEqual(
            contract.ordered_frame_names_sha256(frames),
            _sha256(b"z_tap-02.jpg\na_tap-01.jpg\n"),
        )
        self.assertEqual(
            contract.image_identity_manifest_sha256(frames, identities),
            _sha256(
                b"z_tap-02.jpg\t"
                + b"a" * 64
                + b"\t7\na_tap-01.jpg\t"
                + b"b" * 64
                + b"\t11\n"
            ),
        )
        self.assertEqual(
            contract.ordered_frame_names_sha256([]), _sha256(b"")
        )


class GenericInputContractTests(unittest.TestCase):
    def test_loads_strict_core_and_preserves_extra_provenance(self) -> None:
        payload = _minimal_contract()
        payload["provenance"] = {"generator": "unit-test"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            loaded, file_sha256 = contract.load_input_contract(path)

        self.assertEqual(loaded["dataset_id"], "synthetic_metric")
        self.assertEqual(loaded["provenance"], {"generator": "unit-test"})
        self.assertEqual(file_sha256, _sha256(json.dumps(payload).encode("utf-8")))

    def test_rejects_wrong_coordinate_scale(self) -> None:
        for coordinate_frame, bad_scale in (
            ("metric_arkit_cv", 0.21677133346045502),
            ("raw_lapa_model", 1.0),
        ):
            with self.subTest(coordinate_frame=coordinate_frame):
                payload = _minimal_contract()
                payload["coordinate_frame"] = coordinate_frame
                payload["metres_per_model_unit"] = bad_scale
                with self.assertRaisesRegex(
                    contract.RouteInputNotEquivalent,
                    r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                ):
                    contract.validate_input_contract(payload)

    def test_optimized_sfm_cv_accepts_only_explicit_finite_positive_scale(self) -> None:
        payload = _minimal_contract()
        payload["coordinate_frame"] = "optimized_sfm_cv"
        payload["metres_per_model_unit"] = 0.37
        self.assertIs(contract.validate_input_contract(payload), payload)

        for bad_scale in (0.0, -0.1, float("nan"), float("inf")):
            with self.subTest(bad_scale=bad_scale):
                rejected = _minimal_contract()
                rejected["coordinate_frame"] = "optimized_sfm_cv"
                rejected["metres_per_model_unit"] = bad_scale
                with self.assertRaisesRegex(
                    contract.RouteInputNotEquivalent,
                    r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                ):
                    contract.validate_input_contract(rejected)

    def test_fixed_coordinate_frames_accept_only_their_exact_scale(self) -> None:
        raw_lapa = _minimal_contract()
        raw_lapa["coordinate_frame"] = "raw_lapa_model"
        raw_lapa["metres_per_model_unit"] = 0.21677133346045502
        self.assertIs(contract.validate_input_contract(raw_lapa), raw_lapa)

        unsupported = _minimal_contract()
        unsupported["coordinate_frame"] = "caller_defined"
        with self.assertRaisesRegex(
            contract.RouteInputNotEquivalent,
            r"^ROUTE_INPUT_NOT_EQUIVALENT$",
        ):
            contract.validate_input_contract(unsupported)

    def test_rejects_cap50_dataset_id_for_bench_spatial_names(self) -> None:
        payload = _minimal_contract(dataset_id="cap50_quality")
        with self.assertRaisesRegex(
            contract.RouteInputNotEquivalent,
            r"^ROUTE_INPUT_NOT_EQUIVALENT$",
        ):
            contract.validate_input_contract(payload)

    def test_cap50_dataset_accepts_exact_tap_basenames(self) -> None:
        payload = _minimal_contract(
            dataset_id="cap50_quality",
            frames=["capture_tap-0001.jpg", "capture_tap-0002.jpg"],
        )
        self.assertIs(contract.validate_input_contract(payload), payload)

    def test_rejects_wrong_order_hash_split_hash_or_image_manifest(self) -> None:
        mutations = (
            ("dmcache", "frame_order_sha256"),
            ("splits", "quality", "heldout", "semantic_sha256"),
            ("images", "root_manifest_sha256"),
        )
        for keys in mutations:
            with self.subTest(keys=keys):
                payload = _minimal_contract()
                target: object = payload
                for key in keys[:-1]:
                    target = target[key]  # type: ignore[index]
                target[keys[-1]] = "0" * 64  # type: ignore[index]
                with self.assertRaisesRegex(
                    contract.RouteInputNotEquivalent,
                    r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                ):
                    contract.validate_input_contract(payload)

    def test_only_quality_forbidden_split_may_have_empty_heldout(self) -> None:
        payload = _minimal_contract()
        split = payload["splits"]["quality"]  # type: ignore[index]
        split["quality_scoring_forbidden"] = True
        all_frames = payload["dmcache"]["frame_order"]  # type: ignore[index]
        split["reconstruction"] = {
            "frames": all_frames,
            "file_sha256": contract.ordered_frame_names_sha256(all_frames),
            "semantic_sha256": contract.ordered_frame_names_sha256(all_frames),
        }
        split["heldout"] = {
            "frames": [],
            "file_sha256": contract.ordered_frame_names_sha256([]),
            "semantic_sha256": contract.ordered_frame_names_sha256([]),
        }
        self.assertIs(contract.validate_input_contract(payload), payload)

        split["quality_scoring_forbidden"] = False
        with self.assertRaisesRegex(
            contract.RouteInputNotEquivalent,
            r"^ROUTE_INPUT_NOT_EQUIVALENT$",
        ):
            contract.validate_input_contract(payload)

        split["quality_scoring_forbidden"] = True
        split["reconstruction"] = split["heldout"]
        with self.assertRaisesRegex(
            contract.RouteInputNotEquivalent,
            r"^ROUTE_INPUT_NOT_EQUIVALENT$",
        ):
            contract.validate_input_contract(payload)


class DepthEncodingTests(unittest.TestCase):
    def test_camera_z_ray_roundtrip_meets_contract(self) -> None:
        depth = np.array(
            [[0.0, 1.25, 2.5], [3.0, np.nan, 5.0]], dtype=np.float32
        )
        K = np.array(
            [[525.0, 0.0, 1.1], [0.0, 520.0, 0.6], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
        mask = np.isfinite(depth) & (depth > 0)
        ray = contract.camera_z_to_euclidean_ray(depth, K)
        restored = contract.euclidean_ray_to_camera_z(ray, K)
        error = contract.max_relative_roundtrip_error(depth, restored, mask)
        self.assertLessEqual(error, 1e-6)
        self.assertTrue(np.all(ray[~mask] == 0.0))


if __name__ == "__main__":
    unittest.main()
