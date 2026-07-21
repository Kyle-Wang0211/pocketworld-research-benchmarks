from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_TOOLS))

import b0_prepare_eval as subject
import b0_input_contract as input_contract
import mesh_ab_eval


def _list_bytes(names: list[str]) -> bytes:
    return ("\n".join(names) + "\n").encode("utf-8")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _jpeg_with_exif_orientation(rgb: np.ndarray, orientation: int) -> bytes:
    """Encode a JPEG and inject a minimal big-endian EXIF orientation tag."""

    encoded_ok, encoded = cv2.imencode(
        ".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95]
    )
    if not encoded_ok:
        raise AssertionError("could not encode synthetic JPEG")
    jpeg = encoded.tobytes()
    if not jpeg.startswith(b"\xff\xd8"):
        raise AssertionError("synthetic JPEG is missing SOI")
    tiff = (
        b"MM\x00\x2a\x00\x00\x00\x08"
        b"\x00\x01"
        b"\x01\x12\x00\x03\x00\x00\x00\x01"
        + int(orientation).to_bytes(2, "big")
        + b"\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    app1_payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + (len(app1_payload) + 2).to_bytes(2, "big") + app1_payload
    return jpeg[:2] + app1 + jpeg[2:]


class SyntheticPreparationFixture:
    def __init__(self, root: Path, *, consistent_sources: int = 4) -> None:
        self.root = root
        self.height = 65
        self.width = 65
        self.heldout = ["held_b.png", "held_a.png"]
        self.reconstruction = [f"rec_{index}.png" for index in range(8)]
        self.frames = [
            "held_a.png",
            *self.reconstruction[:4],
            "held_b.png",
            *self.reconstruction[4:],
        ]

        depth = np.full(
            (len(self.frames), self.height, self.width), 2.0, dtype=np.float32
        )
        for name in self.reconstruction[consistent_sources:]:
            depth[self.frames.index(name)] = np.float32(4.0)

        self.dmcache = root / "dmcache.npz"
        np.savez(
            self.dmcache,
            frames=np.asarray(self.frames),
            dm=depth,
            sig=np.asarray("synthetic-camera-z"),
        )

        intrinsics = np.repeat(
            np.eye(3, dtype=np.float32)[None, :, :], len(self.frames), axis=0
        )
        intrinsics[:, 0, 0] = 32.0
        intrinsics[:, 1, 1] = 32.0
        intrinsics[:, 0, 2] = 32.0
        intrinsics[:, 1, 2] = 32.0
        world_to_camera = np.repeat(
            np.eye(4, dtype=np.float32)[None, :, :], len(self.frames), axis=0
        )
        for index, name in enumerate(self.reconstruction):
            # Non-zero baselines make the round trip meaningful.  A world-space
            # camera center +x is encoded as t=-center for identity rotation.
            # 0.20 raw-LAPA units exceeds the frozen 0.04 metre threshold after
            # applying the preregistered metres-per-LAPA scale.
            world_to_camera[self.frames.index(name), 0, 3] = -(0.20 + index * 0.02)
        world_to_camera[self.frames.index("held_b.png"), 1, 3] = -0.001

        # Reverse cache order so a positional join would silently be wrong.
        reverse = np.arange(len(self.frames) - 1, -1, -1)
        self.model = root / "model.npz"
        np.savez(
            self.model,
            names=np.asarray(self.frames)[reverse],
            K=intrinsics[reverse],
            w2c=world_to_camera[reverse],
        )

        self.reconstruction_list = root / "reconstruction.txt"
        self.reconstruction_list.write_bytes(_list_bytes(self.reconstruction))
        self.heldout_list = root / "heldout.txt"
        self.heldout_list.write_bytes(_list_bytes(self.heldout))

        self.image_root = root / "images"
        self.image_root.mkdir()
        raw_height = self.height * 2
        raw_width = self.width * 2
        uniform = np.full((raw_height, raw_width, 3), 128, dtype=np.uint8)
        textured = uniform.copy()
        yy, xx = np.indices((34, 34))
        checker = ((((xx // 4) + (yy // 4)) & 1) * 255).astype(np.uint8)
        textured[48:82, 48:82] = checker[:, :, None]
        for name in self.frames:
            image = textured if name in self.heldout else uniform
            if not cv2.imwrite(str(self.image_root / name), image):
                raise AssertionError(f"could not write fixture image {name}")

    def frozen_patches(self) -> dict[str, object]:
        return {
            "EXPECTED_DMCACHE_SHA256": _sha(self.dmcache),
            "EXPECTED_MODEL_CACHE_SHA256": _sha(self.model),
            "EXPECTED_DMCACHE_SIGNATURE": "synthetic-camera-z",
            "EXPECTED_DEPTH_SHAPE": (
                len(self.frames),
                self.height,
                self.width,
            ),
            "FROZEN_SPLIT_HASHES": {
                "synthetic": {
                    "reconstruction_sha256": _sha(self.reconstruction_list),
                    "heldout_sha256": _sha(self.heldout_list),
                    "reconstruction_count": len(self.reconstruction),
                    "heldout_count": len(self.heldout),
                }
            },
        }

    def prepare(self, output: Path) -> dict[str, object]:
        with mock.patch.multiple(subject, **self.frozen_patches()):
            return subject.prepare_evaluation_inputs(
                dmcache=self.dmcache,
                model_cache=self.model,
                reconstruction_list=self.reconstruction_list,
                heldout_list=self.heldout_list,
                image_root=self.image_root,
                out=output,
            )

    def generic_contract(
        self,
        *,
        dataset_id: str = "synthetic_metric",
        coordinate_frame: str = "metric_arkit_cv",
        metres_per_model_unit: float = 1.0,
    ) -> dict[str, object]:
        with np.load(self.model, allow_pickle=False) as archive:
            model_order = archive["names"].tolist()
        identities = {
            name: {
                "sha256": _sha(self.image_root / name),
                "size_bytes": (self.image_root / name).stat().st_size,
            }
            for name in self.frames
        }
        return {
            "schema_version": "b0-input-contract-v1",
            "dataset_id": dataset_id,
            "coordinate_frame": coordinate_frame,
            "metres_per_model_unit": metres_per_model_unit,
            "transductive_policy": {
                "present": False,
                "route_allowed": True,
                "quality_scoring_forbidden": False,
                "warning": "synthetic fixture only",
                "forbidden_claims": ["ground-truth accuracy"],
            },
            "dmcache": {
                "sha256": _sha(self.dmcache),
                "signature": "synthetic-camera-z",
                "depth": {
                    "shape": [len(self.frames), self.height, self.width],
                    "dtype": "float32",
                },
                "frame_order": self.frames,
                "frame_order_sha256": input_contract.ordered_frame_names_sha256(
                    self.frames
                ),
            },
            "model_cache": {
                "sha256": _sha(self.model),
                "frame_order": model_order,
                "frame_order_sha256": input_contract.ordered_frame_names_sha256(
                    model_order
                ),
            },
            "splits": {
                "quality": {
                    "reconstruction": {
                        "frames": self.reconstruction,
                        "file_sha256": _sha(self.reconstruction_list),
                        "semantic_sha256": input_contract.ordered_frame_names_sha256(
                            self.reconstruction
                        ),
                    },
                    "heldout": {
                        "frames": self.heldout,
                        "file_sha256": _sha(self.heldout_list),
                        "semantic_sha256": input_contract.ordered_frame_names_sha256(
                            self.heldout
                        ),
                    },
                }
            },
            "images": {
                "root": str(self.image_root.resolve()),
                "raw_size_wh": [self.width * 2, self.height * 2],
                "root_manifest_sha256": input_contract.image_identity_manifest_sha256(
                    self.frames, identities
                ),
                "by_name": identities,
            },
            "provenance": {"fixture": True},
        }

    def write_generic_contract(self, **overrides: object) -> Path:
        payload = self.generic_contract(**overrides)
        path = self.root / "input-contract.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def prepare_generic(self, output: Path, *, split_id: str = "quality") -> dict[str, object]:
        return subject.prepare_evaluation_inputs(
            dmcache=self.dmcache,
            model_cache=self.model,
            reconstruction_list=self.reconstruction_list,
            heldout_list=self.heldout_list,
            image_root=self.image_root,
            input_contract=self.write_generic_contract(),
            split_id=split_id,
            out=output,
        )


class PreparedArchiveTests(unittest.TestCase):
    def test_full_frozen_profile_uses_historical_331_82_split(self) -> None:
        self.assertEqual(
            subject.FROZEN_SPLIT_HASHES["full413"]["reconstruction_count"], 331
        )
        self.assertEqual(subject.FROZEN_SPLIT_HASHES["full413"]["heldout_count"], 82)
        self.assertEqual(
            subject.FROZEN_SPLIT_HASHES["full413"]["reconstruction_sha256"],
            "d2dca3eac2f8efbf18b1efdd9e08b0a6e9b504eb71af378b4444bff035e54a41",
        )
        self.assertEqual(
            subject.FROZEN_SPLIT_HASHES["full413"]["heldout_sha256"],
            "5e16f68e603af0b3e27b6957ba0dad0fc0fbeec1d068a04e0b22a2ed78696805",
        )

    def test_prepares_exact_evaluator_schema_with_projected_input_only_masks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root, consistent_sources=4)
            output = root / "prepared.npz"

            result = fixture.prepare(output)

            self.assertEqual(result["status"], "PREPARED")
            with np.load(output, allow_pickle=False) as archive:
                self.assertEqual(tuple(archive.files), mesh_ab_eval.CONTRACT_ARRAY_KEYS)
                arrays = {name: np.asarray(archive[name]) for name in archive.files}

            self.assertEqual(arrays["frames"].tolist(), fixture.heldout)
            self.assertEqual(arrays["depth"].dtype, np.dtype(np.float32))
            self.assertEqual(arrays["K"].dtype, np.dtype(np.float32))
            self.assertEqual(arrays["w2c"].dtype, np.dtype(np.float32))
            self.assertEqual(float(arrays["w2c"][0, 1, 3]), -0.0010000000474974513)
            self.assertEqual(float(arrays["w2c"][1, 1, 3]), 0.0)
            for name in ("roi", "low_texture", "weak_support", "planar_single_surface"):
                self.assertEqual(arrays[name].dtype, np.dtype(np.bool_))

            # Four offset reconstruction cameras are round-trip consistent.
            # The remaining four have inconsistent camera-Z depths.
            self.assertTrue(arrays["roi"][:, 47, 47].all())
            self.assertTrue(arrays["weak_support"][:, 47, 47].all())
            self.assertFalse(arrays["roi"][:, 4, 4].any())

            # Linear-light Sobel RMS separates the uniform and checkerboard areas.
            self.assertTrue(arrays["low_texture"][:, 47, 47].all())
            self.assertFalse(arrays["low_texture"][:, 32, 32].any())
            self.assertTrue(arrays["planar_single_surface"][:, 47, 47].all())

            provenance_path = subject.provenance_path(output)
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            digest = mesh_ab_eval.frozen_input_digest(arrays)
            self.assertEqual(provenance["evaluator_digest"], digest)
            self.assertEqual(provenance["evaluation_digest"], digest)
            self.assertEqual(result["evaluator_digest"], digest)
            self.assertEqual(result["evaluation_digest"], digest)
            self.assertEqual(provenance["frame_order"], fixture.heldout)
            self.assertEqual(provenance["split_profile"], "synthetic")
            self.assertEqual(provenance["dataset_id"], "legacy_trio_synthetic")
            self.assertEqual(
                provenance["coordinate_scale"]["stored_coordinate_frame"],
                "raw LAPA",
            )
            self.assertTrue(provenance["limitations"]["transductive_observation_consistency"])
            self.assertTrue(provenance["limitations"]["not_ground_truth"])
            self.assertIn("output_npz", provenance["component_sha256"])
            self.assertIn("mesh_ab_eval.py", provenance["component_sha256"])
            self.assertEqual(
                provenance["component_sha256"]["frozen_sim3_canonical"],
                "ca5e4b72dcb4e6a7bee8af8182c2947e006de5a59e8ca7c1e030ffee288b70f4",
            )
            self.assertEqual(provenance["constants"]["candidate_camera_count"], 8)
            self.assertEqual(
                provenance["coordinate_scale"]["metres_per_raw_lapa_unit"],
                0.21677133346045502,
            )
            self.assertEqual(
                provenance["coordinate_scale"]["frozen_sim3_sha256"],
                "ca5e4b72dcb4e6a7bee8af8182c2947e006de5a59e8ca7c1e030ffee288b70f4",
            )
            self.assertAlmostEqual(
                provenance["constants"]["weak_minimum_baseline_raw_lapa"],
                0.04 / 0.21677133346045502,
                places=15,
            )
            self.assertAlmostEqual(
                provenance["constants"]["planar_max_absolute_residual_raw_lapa"],
                0.005 / 0.21677133346045502,
                places=15,
            )
            self.assertEqual(
                provenance["heldout_images"][0]["original_size_hw"], [130, 130]
            )
            self.assertEqual(
                provenance["heldout_images"][0]["prepared_size_hw"], [65, 65]
            )
            self.assertEqual(
                provenance["heldout_images"][0]["resize"],
                "cv2.resize INTER_AREA after RGB conversion",
            )

    def test_generic_metric_contract_binds_dataset_split_policy_and_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            output = root / "metric-prepared.npz"

            result = fixture.prepare_generic(output)
            provenance = json.loads(
                subject.provenance_path(output).read_text(encoding="utf-8")
            )

            self.assertEqual(result["dataset_id"], "synthetic_metric")
            self.assertEqual(result["split_id"], "quality")
            self.assertEqual(provenance["dataset_id"], "synthetic_metric")
            self.assertEqual(provenance["split_id"], "quality")
            self.assertTrue(provenance["route_allowed"])
            self.assertFalse(provenance["quality_scoring_forbidden"])
            self.assertEqual(
                provenance["coordinate_scale"]["stored_coordinate_frame"],
                "metric_arkit_cv",
            )
            self.assertEqual(
                provenance["coordinate_scale"]["metres_per_model_unit"], 1.0
            )
            self.assertNotIn("frozen_sim3_canonical", provenance["component_sha256"])
            self.assertNotIn("frozen_sim3_sha256", provenance["coordinate_scale"])
            self.assertEqual(
                provenance["constants"]["weak_minimum_baseline_model_units"],
                0.04,
            )
            self.assertEqual(
                provenance["constants"]["planar_max_absolute_residual_model_units"],
                0.005,
            )
            self.assertEqual(
                provenance["component_sha256"]["input_contract"],
                _sha(fixture.root / "input-contract.json"),
            )

    def test_generic_optimized_sfm_uses_contract_scale_for_physical_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            scale = 1.007804831494465
            contract_path = fixture.write_generic_contract(
                coordinate_frame="optimized_sfm_cv",
                metres_per_model_unit=scale,
            )
            output = root / "optimized-prepared.npz"

            subject.prepare_evaluation_inputs(
                dmcache=fixture.dmcache,
                model_cache=fixture.model,
                reconstruction_list=fixture.reconstruction_list,
                heldout_list=fixture.heldout_list,
                image_root=fixture.image_root,
                input_contract=contract_path,
                split_id="quality",
                out=output,
            )
            provenance = json.loads(
                subject.provenance_path(output).read_text(encoding="utf-8")
            )

            self.assertEqual(
                provenance["coordinate_scale"]["stored_coordinate_frame"],
                "optimized_sfm_cv",
            )
            self.assertEqual(
                provenance["coordinate_scale"]["metres_per_model_unit"], scale
            )
            self.assertAlmostEqual(
                provenance["constants"]["weak_minimum_baseline_model_units"],
                0.04 / scale,
                places=15,
            )
            self.assertAlmostEqual(
                provenance["constants"]["planar_max_absolute_residual_model_units"],
                0.005 / scale,
                places=15,
            )

    def test_exactly_five_consistent_cameras_is_not_weak_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root, consistent_sources=5)
            output = root / "prepared.npz"

            fixture.prepare(output)

            with np.load(output, allow_pickle=False) as archive:
                self.assertTrue(archive["roi"][:, 47, 47].all())
                self.assertFalse(archive["weak_support"][:, 47, 47].any())

    def test_local_planarity_rejects_a_nonplanar_depth_bump(self) -> None:
        height = width = 31
        depth = np.full((height, width), 2.0, dtype=np.float32)
        intrinsics = np.asarray(
            [[30.0, 0.0, 15.0], [0.0, 30.0, 15.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
        world_to_camera = np.eye(4, dtype=np.float32)
        roi = np.zeros((height, width), dtype=bool)
        roi[6:-6, 6:-6] = True

        planar = subject.local_planar_mask(depth, intrinsics, world_to_camera, roi)
        self.assertTrue(planar[15, 15])

        # 0.01 raw-LAPA residual is above 0.005 raw units but below the correctly
        # converted 0.005 metre threshold (about 0.0231 raw units).
        metric_small_bump = depth.copy()
        metric_small_bump[15, 15] += np.float32(0.01)
        converted_threshold = subject.local_planar_mask(
            metric_small_bump, intrinsics, world_to_camera, roi
        )
        self.assertTrue(converted_threshold[15, 15])

        bumped = depth.copy()
        bumped[13:18, 13:18] += np.float32(0.10)
        nonplanar = subject.local_planar_mask(
            bumped, intrinsics, world_to_camera, roi
        )
        self.assertFalse(nonplanar[15, 15])

    def test_depth_normals_are_emitted_once_in_world_coordinates(self) -> None:
        depth = np.full((15, 15), 2.0, dtype=np.float32)
        intrinsics = np.asarray(
            [[20.0, 0.0, 7.0], [0.0, 20.0, 7.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
        angle = np.deg2rad(30.0)
        cosine = np.cos(angle)
        sine = np.sin(angle)
        world_to_camera = np.asarray(
            [
                [cosine, 0.0, sine, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [-sine, 0.0, cosine, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float32,
        )

        normals = subject._depth_normals_world(
            depth, intrinsics, world_to_camera
        )

        camera_to_world = np.linalg.inv(world_to_camera.astype(np.float64))
        expected = camera_to_world[:3, :3] @ np.asarray([0.0, 0.0, 1.0])
        expected /= np.linalg.norm(expected)
        self.assertGreater(float(np.dot(normals[7, 7], expected)), 1.0 - 1e-12)

    def test_image_preparation_is_byte_identical_to_tsdf_opencv_sequence(self) -> None:
        yy, xx = np.indices((9, 13), dtype=np.uint8)
        bgr = np.stack((xx * 7, yy * 13, (xx + yy) * 5), axis=2)
        encoded_ok, encoded = cv2.imencode(".png", bgr)
        self.assertTrue(encoded_ok)

        actual, metadata = subject._decode_srgb_image(
            encoded.tobytes(), (9, 13), "color.png"
        )

        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        expected = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
        expected = cv2.resize(expected, (13, 9), interpolation=cv2.INTER_AREA)
        np.testing.assert_array_equal(actual, np.ascontiguousarray(expected, np.uint8))
        self.assertEqual(
            metadata["resize"], "cv2.resize INTER_AREA after RGB conversion"
        )

    def test_orientation_six_jpeg_uses_unrotated_encoded_raster(self) -> None:
        raw_height, raw_width = 24, 40
        yy, xx = np.indices((raw_height, raw_width), dtype=np.uint8)
        rgb = np.stack((xx * 5, yy * 9, (xx + yy) * 3), axis=2)
        payload = _jpeg_with_exif_orientation(rgb, 6)
        encoded = np.frombuffer(payload, dtype=np.uint8)

        auto_oriented = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        encoded_raster = cv2.imdecode(
            encoded, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION
        )
        self.assertEqual(auto_oriented.shape[:2], (raw_width, raw_height))
        self.assertEqual(encoded_raster.shape[:2], (raw_height, raw_width))

        actual, metadata = subject._decode_srgb_image(
            payload,
            (12, 20),
            "orientation-six.jpg",
            expected_raw_size_wh=(raw_width, raw_height),
        )
        expected = cv2.cvtColor(encoded_raster, cv2.COLOR_BGR2RGB)
        expected = cv2.resize(expected, (20, 12), interpolation=cv2.INTER_AREA)

        np.testing.assert_array_equal(actual, np.ascontiguousarray(expected, np.uint8))
        self.assertEqual(metadata["raw_size_wh"], [raw_width, raw_height])
        self.assertEqual(
            metadata["decode"],
            "cv2.imdecode IMREAD_COLOR|IMREAD_IGNORE_ORIENTATION",
        )

    def test_image_preparation_rejects_wrong_raw_dimensions_before_resize(self) -> None:
        rgb = np.zeros((24, 40, 3), dtype=np.uint8)
        payload = _jpeg_with_exif_orientation(rgb, 6)

        with mock.patch.object(cv2, "resize", wraps=cv2.resize) as resize:
            with self.assertRaisesRegex(
                subject.PreparationError, "raw encoded image dimensions mismatch"
            ):
                subject._decode_srgb_image(
                    payload,
                    (12, 20),
                    "wrong-size.jpg",
                    expected_raw_size_wh=(41, 24),
                )

        resize.assert_not_called()

    def test_weak_camera_baseline_is_converted_from_metres_to_raw_lapa(self) -> None:
        centers = np.zeros((16, 3), dtype=np.float64)
        centers[:8, 0] = np.linspace(0.10, 0.17, 8)
        centers[8:, 0] = np.linspace(0.19, 0.26, 8)

        selected = subject._ordered_nearest_indices(
            np.zeros(3, dtype=np.float64),
            centers,
            minimum_baseline=subject.MIN_WEAK_BASELINE_RAW_LAPA,
        )

        self.assertEqual(selected, list(range(8, 16)))
        self.assertAlmostEqual(
            subject.MIN_WEAK_BASELINE_RAW_LAPA,
            0.04 / 0.21677133346045502,
            places=15,
        )


class FailClosedPreparationTests(unittest.TestCase):
    def test_generic_contract_requires_raw_image_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            contract = fixture.generic_contract()
            del contract["images"]["raw_size_wh"]
            contract_path = root / "missing-raw-size-contract.json"
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            output = root / "prepared.npz"

            with self.assertRaisesRegex(subject.PreparationError, "raw_size_wh"):
                subject.prepare_evaluation_inputs(
                    dmcache=fixture.dmcache,
                    model_cache=fixture.model,
                    reconstruction_list=fixture.reconstruction_list,
                    heldout_list=fixture.heldout_list,
                    image_root=fixture.image_root,
                    input_contract=contract_path,
                    split_id="quality",
                    out=output,
                )

            self.assertFalse(output.exists())
            self.assertFalse(subject.provenance_path(output).exists())

    def test_rejects_overlapping_lists_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            fixture.heldout_list.write_bytes(
                _list_bytes([fixture.reconstruction[0], fixture.heldout[0]])
            )
            output = root / "prepared.npz"
            patches = fixture.frozen_patches()
            patches["FROZEN_SPLIT_HASHES"] = {
                "synthetic": {
                    "reconstruction_sha256": _sha(fixture.reconstruction_list),
                    "heldout_sha256": _sha(fixture.heldout_list),
                    "reconstruction_count": 8,
                    "heldout_count": 2,
                }
            }

            with mock.patch.multiple(subject, **patches):
                with self.assertRaisesRegex(subject.PreparationError, "overlap"):
                    subject.prepare_evaluation_inputs(
                        dmcache=fixture.dmcache,
                        model_cache=fixture.model,
                        reconstruction_list=fixture.reconstruction_list,
                        heldout_list=fixture.heldout_list,
                        image_root=fixture.image_root,
                        out=output,
                    )

            self.assertFalse(output.exists())
            self.assertFalse(subject.provenance_path(output).exists())

    def test_rejects_bad_exact_name_join_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            fixture.heldout_list.write_bytes(_list_bytes(["missing.png", "held_a.png"]))
            output = root / "prepared.npz"
            patches = fixture.frozen_patches()
            patches["FROZEN_SPLIT_HASHES"] = {
                "synthetic": {
                    "reconstruction_sha256": _sha(fixture.reconstruction_list),
                    "heldout_sha256": _sha(fixture.heldout_list),
                    "reconstruction_count": 8,
                    "heldout_count": 2,
                }
            }

            with mock.patch.multiple(subject, **patches):
                with self.assertRaisesRegex(subject.PreparationError, "exact-name join"):
                    subject.prepare_evaluation_inputs(
                        dmcache=fixture.dmcache,
                        model_cache=fixture.model,
                        reconstruction_list=fixture.reconstruction_list,
                        heldout_list=fixture.heldout_list,
                        image_root=fixture.image_root,
                        out=output,
                    )

            self.assertFalse(output.exists())

    def test_rejects_existing_output_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            output = root / "prepared.npz"
            output.write_bytes(b"keep-me")

            with self.assertRaisesRegex(FileExistsError, "output already exists"):
                fixture.prepare(output)

            self.assertEqual(output.read_bytes(), b"keep-me")
            self.assertFalse(subject.provenance_path(output).exists())

    def test_rejects_any_component_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            output = root / "prepared.npz"
            patches = fixture.frozen_patches()
            patches["EXPECTED_MODEL_CACHE_SHA256"] = "0" * 64

            with mock.patch.multiple(subject, **patches):
                with self.assertRaisesRegex(subject.PreparationError, "model cache SHA-256"):
                    subject.prepare_evaluation_inputs(
                        dmcache=fixture.dmcache,
                        model_cache=fixture.model,
                        reconstruction_list=fixture.reconstruction_list,
                        heldout_list=fixture.heldout_list,
                        image_root=fixture.image_root,
                        out=output,
                    )

            self.assertFalse(output.exists())

    def test_generic_contract_rejects_wrong_split_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            output = root / "prepared.npz"

            with self.assertRaisesRegex(subject.PreparationError, "split"):
                fixture.prepare_generic(output, split_id="missing")

            self.assertFalse(output.exists())
            self.assertFalse(subject.provenance_path(output).exists())

    def test_generic_contract_rejects_list_file_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            contract_path = fixture.write_generic_contract()
            fixture.reconstruction_list.write_bytes(
                _list_bytes(list(reversed(fixture.reconstruction)))
            )
            output = root / "prepared.npz"

            with self.assertRaisesRegex(subject.PreparationError, "reconstruction list"):
                subject.prepare_evaluation_inputs(
                    dmcache=fixture.dmcache,
                    model_cache=fixture.model,
                    reconstruction_list=fixture.reconstruction_list,
                    heldout_list=fixture.heldout_list,
                    image_root=fixture.image_root,
                    input_contract=contract_path,
                    split_id="quality",
                    out=output,
                )

            self.assertFalse(output.exists())

    def test_generic_contract_rejects_image_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SyntheticPreparationFixture(root)
            contract_path = fixture.write_generic_contract()
            (fixture.image_root / fixture.frames[0]).write_bytes(b"changed")
            output = root / "prepared.npz"

            with self.assertRaisesRegex(subject.PreparationError, "image identity"):
                subject.prepare_evaluation_inputs(
                    dmcache=fixture.dmcache,
                    model_cache=fixture.model,
                    reconstruction_list=fixture.reconstruction_list,
                    heldout_list=fixture.heldout_list,
                    image_root=fixture.image_root,
                    input_contract=contract_path,
                    split_id="quality",
                    out=output,
                )

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
