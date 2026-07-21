from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
if str(PYTHON_TOOLS) not in sys.path:
    sys.path.insert(0, str(PYTHON_TOOLS))

import b0_input_contract as shared_contract  # noqa: E402
import pw_tsdf_trio as subject  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordered_sha(names: list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{name}\n" for name in names).encode("utf-8")
    ).hexdigest()


def make_fixture(
    root: Path,
    *,
    coordinate_frame: str = "metric_arkit_cv",
    metres_per_model_unit: float = 1.0,
    valid_images: bool = False,
) -> tuple[SimpleNamespace, Path, dict[str, object]]:
    inputs = root / "inputs"
    inputs.mkdir()
    images = inputs / "images"
    images.mkdir()
    names = ["cap50_tap-001.jpg", "cap50_tap-002.jpg", "cap50_tap-003.jpg"]
    reconstruction = names[:2]
    heldout = names[2:]
    for index, name in enumerate(names):
        if valid_images:
            pixels = np.full((2, 3, 3), 32 + index * 40, dtype=np.uint8)
            encoded, payload = subject.cv2.imencode(".jpg", pixels)
            if not encoded:
                raise AssertionError("test JPEG encoding failed")
            (images / name).write_bytes(payload.tobytes())
        else:
            (images / name).write_bytes(f"image-{index}".encode())

    dmcache = inputs / "dm.npz"
    depths = np.array(
        [
            [[1.0, 0.0, 2.0], [3.0, 4.0, 0.0]],
            [[2.0, 2.5, 0.0], [0.0, 3.0, 4.0]],
            [[1.5, 0.0, 2.5], [3.5, 0.0, 4.5]],
        ],
        dtype=np.float32,
    )
    np.savez_compressed(
        dmcache,
        frames=np.asarray(names),
        dm=depths,
        sig=np.asarray("ofull-frozen-mask-v1"),
    )

    model_names = [names[1], names[2], names[0]]
    K = np.repeat(np.eye(3, dtype=np.float32)[None], 3, axis=0)
    K[:, 0, 0] = 5.0
    K[:, 1, 1] = 5.0
    K[:, 0, 2] = 1.0
    K[:, 1, 2] = 0.5
    w2c = np.repeat(np.eye(4, dtype=np.float32)[None], 3, axis=0)
    model = inputs / "model.npz"
    np.savez_compressed(model, names=np.asarray(model_names), K=K, w2c=w2c)

    frame_list = inputs / "reconstruction.txt"
    frame_list.write_text("".join(f"{name}\n" for name in reconstruction), encoding="utf-8")
    heldout_file = inputs / "heldout.txt"
    heldout_file.write_text("".join(f"{name}\n" for name in heldout), encoding="utf-8")
    identities = {
        name: {"sha256": sha(images / name), "size_bytes": (images / name).stat().st_size}
        for name in names
    }
    payload: dict[str, object] = {
        "schema_version": subject.INPUT_CONTRACT_SCHEMA,
        "dataset_id": "cap50-real-device",
        "coordinate_frame": coordinate_frame,
        "metres_per_model_unit": metres_per_model_unit,
        "transductive_policy": {
            "present": False,
            "route_allowed": True,
            "quality_scoring_forbidden": False,
        },
        "dmcache": {
            "sha256": sha(dmcache),
            "signature": "ofull-frozen-mask-v1",
            "depth": {"shape": list(depths.shape), "dtype": "float32"},
            "frame_order": names,
            "frame_order_sha256": ordered_sha(names),
        },
        "model_cache": {
            "sha256": sha(model),
            "frame_order": model_names,
            "frame_order_sha256": ordered_sha(model_names),
        },
        "splits": {
            "gate": {
                "reconstruction": {
                    "frames": reconstruction,
                    "file_sha256": sha(frame_list),
                    "semantic_sha256": ordered_sha(reconstruction),
                },
                "heldout": {
                    "frames": heldout,
                    "file_sha256": sha(heldout_file),
                    "semantic_sha256": ordered_sha(heldout),
                },
            }
        },
        "images": {
            "root_manifest_sha256": subject.image_identity_manifest_sha256(names, identities),
            "by_name": identities,
        },
    }
    contract = inputs / "contract.json"
    contract.write_text(json.dumps(payload), encoding="utf-8")
    args = SimpleNamespace(
        tag="ofull",
        voxel_mm=6.0,
        out=root / "result",
        frame_list=frame_list,
        dmcache=dmcache,
        model_cache=model,
        image_root=images,
        input_contract=contract,
        split_id="gate",
        p1cache=root / "must-not-be-read.npz",
    )
    return args, contract, payload


class CliTests(unittest.TestCase):
    def base(self) -> list[str]:
        return [
            "ofull", "6", "--out", "/tmp/new", "--frame-list", "/tmp/f",
            "--dmcache", "/tmp/dm", "--model-cache", "/tmp/model",
            "--image-root", "/tmp/images", "--input-contract", "/tmp/contract",
            "--split-id", "gate",
        ]

    def test_all_identity_inputs_are_required(self):
        for flag in (
            "--out", "--frame-list", "--dmcache", "--model-cache",
            "--image-root", "--input-contract", "--split-id",
        ):
            argv = self.base()
            index = argv.index(flag)
            del argv[index:index + 2]
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                subject.parse_args(argv)

    def test_only_ofull_and_exactly_6mm_are_accepted(self):
        args = subject.parse_args(self.base())
        self.assertEqual((args.tag, args.voxel_mm), ("ofull", 6.0))
        for argv in (
            ["ofsxq", *self.base()[1:]],
            ["ofull", "5", *self.base()[2:]],
            [*self.base(), "--surprise"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                subject.parse_args(argv)

    def test_legacy_ref_limit_positional_is_rejected(self):
        argv = self.base()
        argv.insert(2, "48")
        with self.assertRaises(SystemExit):
            subject.parse_args(argv)

    def test_programmatic_call_cannot_bypass_frozen_route_parameters(self):
        subject.validate_frozen_route_parameters("ofull", 6)
        for tag, voxel in (("ofsxq", 6), ("ofull", 5), ("ofull", float("nan"))):
            with self.subTest(tag=tag, voxel=voxel), self.assertRaises(subject.ContractError):
                subject.validate_frozen_route_parameters(tag, voxel)


class ContractValidationTests(unittest.TestCase):
    def assert_not_equivalent(self, callable_):
        with self.assertRaisesRegex(
            subject.ContractError, rf"^{shared_contract.ROUTE_INPUT_NOT_EQUIVALENT}$"
        ):
            callable_()

    def test_metric_and_raw_lapa_contracts_validate_and_convert_6mm(self):
        cases = [
            ("metric_arkit_cv", 1.0, 0.006),
            (
                "optimized_sfm_cv",
                1.007804831494465,
                0.006 / 1.007804831494465,
            ),
            (
                "raw_lapa_model",
                subject.FROZEN_METRES_PER_LAPA_UNIT,
                0.006 / subject.FROZEN_METRES_PER_LAPA_UNIT,
            ),
        ]
        for coordinate, scale, expected in cases:
            with self.subTest(coordinate=coordinate), tempfile.TemporaryDirectory() as td:
                args, _, _ = make_fixture(
                    Path(td), coordinate_frame=coordinate, metres_per_model_unit=scale
                )
                validated = subject.validate_route_inputs(args)
                self.assertEqual(validated.contract.coordinate_frame, coordinate)
                self.assertEqual(validated.contract.metres_per_model_unit, scale)
                self.assertAlmostEqual(
                    subject.physical_mm_to_model_units(6.0, scale), expected, places=15
                )
                self.assertEqual(
                    validated.contract.reconstruction_frames,
                    ["cap50_tap-001.jpg", "cap50_tap-002.jpg"],
                )
                self.assertFalse(args.p1cache.exists())
                self.assertFalse(args.out.exists())

    def test_wrong_metric_scale_and_wrong_raw_lapa_scale_are_rejected(self):
        for coordinate, scale in (
            ("metric_arkit_cv", 0.5),
            ("raw_lapa_model", 1.0),
        ):
            with self.subTest(coordinate=coordinate), tempfile.TemporaryDirectory() as td:
                args, _, _ = make_fixture(
                    Path(td), coordinate_frame=coordinate, metres_per_model_unit=scale
                )
                self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))

    def test_optimized_sfm_scale_is_contract_owned_not_assumed_or_estimated(self):
        for scale in (0.75, 1.007804831494465, 2.5):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as td:
                args, _, _ = make_fixture(
                    Path(td),
                    coordinate_frame="optimized_sfm_cv",
                    metres_per_model_unit=scale,
                )
                validated = subject.validate_route_inputs(args)
                self.assertEqual(validated.contract.metres_per_model_unit, scale)
                self.assertEqual(
                    subject.physical_mm_to_model_units(6, scale), 0.006 / scale
                )

    def test_wrong_hash_signature_shape_dtype_list_and_image_are_rejected_before_output(self):
        mutations = ("dm_hash", "model_hash", "signature", "shape", "dtype", "list", "image")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                args, contract, payload = make_fixture(root)
                if mutation == "dm_hash":
                    payload["dmcache"]["sha256"] = "0" * 64
                elif mutation == "model_hash":
                    payload["model_cache"]["sha256"] = "0" * 64
                elif mutation == "signature":
                    payload["dmcache"]["signature"] = "wrong"
                elif mutation == "shape":
                    payload["dmcache"]["depth"]["shape"] = [3, 9, 9]
                elif mutation == "dtype":
                    payload["dmcache"]["depth"]["dtype"] = "float64"
                elif mutation == "list":
                    args.frame_list.write_text("cap50_tap-002.jpg\n", encoding="utf-8")
                elif mutation == "image":
                    (args.image_root / "cap50_tap-001.jpg").write_bytes(b"mutated")
                if mutation not in {"list", "image"}:
                    contract.write_text(json.dumps(payload), encoding="utf-8")
                self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))
                self.assertFalse(args.out.exists())

    def test_wrong_image_root_manifest_and_wrong_split_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args, contract, payload = make_fixture(Path(td))
            payload["images"]["root_manifest_sha256"] = "f" * 64
            contract.write_text(json.dumps(payload), encoding="utf-8")
            self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))
        with tempfile.TemporaryDirectory() as td:
            args, _, _ = make_fixture(Path(td))
            args.split_id = "not-frozen"
            self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))

    def test_actual_model_order_must_match_contract_not_only_its_name_set(self):
        with tempfile.TemporaryDirectory() as td:
            args, contract, payload = make_fixture(Path(td))
            with np.load(args.model_cache, allow_pickle=False) as archive:
                names = archive["names"].copy()[::-1]
                K = archive["K"].copy()[::-1]
                w2c = archive["w2c"].copy()[::-1]
            np.savez_compressed(args.model_cache, names=names, K=K, w2c=w2c)
            payload["model_cache"]["sha256"] = sha(args.model_cache)
            # Deliberately retain the pre-registered model frame_order and its
            # digest: changing both would be a different frozen contract.
            contract.write_text(json.dumps(payload), encoding="utf-8")
            self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))
            self.assertFalse(args.out.exists())

    def test_contract_and_split_route_allowed_flags_are_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            args, contract, payload = make_fixture(Path(td))
            payload["transductive_policy"] = {
                "present": True,
                "route_allowed": False,
                "quality_scoring_forbidden": True,
            }
            contract.write_text(json.dumps(payload), encoding="utf-8")
            self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))
        with tempfile.TemporaryDirectory() as td:
            args, contract, payload = make_fixture(Path(td))
            payload["splits"]["gate"]["route_allowed"] = False
            contract.write_text(json.dumps(payload), encoding="utf-8")
            self.assert_not_equivalent(lambda: subject.validate_route_inputs(args))

    def test_shared_schema_optional_metadata_is_not_rejected_by_tsdf_copy(self):
        with tempfile.TemporaryDirectory() as td:
            args, contract, payload = make_fixture(Path(td))
            payload["extra_provenance"] = {"producer": "fixture"}
            payload["transductive_policy"].update(
                {
                    "warning": "held-out quality scoring is not allowed",
                    "forbidden_claims": ["ground-truth accuracy"],
                }
            )
            contract.write_text(json.dumps(payload), encoding="utf-8")
            validated = subject.validate_route_inputs(args)
            self.assertEqual(validated.contract.dataset_id, "cap50-real-device")

    def test_contract_file_hash_and_all_identity_digests_are_retained(self):
        with tempfile.TemporaryDirectory() as td:
            args, contract, _ = make_fixture(Path(td))
            validated = subject.validate_route_inputs(args)
            self.assertEqual(validated.contract.sha256, sha(contract))
            self.assertEqual(validated.dmcache.sha256, sha(args.dmcache))
            self.assertEqual(
                validated.contract.image_root_manifest_sha256,
                subject.image_identity_manifest_sha256(
                    validated.contract.frame_universe,
                    validated.contract.images_by_name,
                ),
            )


class SemanticAndDepthTests(unittest.TestCase):
    def test_semantic_manifest_uses_original_name_depth_K_and_w2c(self):
        names = ["cap50_tap-002.jpg", "cap50_tap-001.jpg"]
        depth = {
            names[0]: np.array([[1.0, np.nan], [0.0, 2.0]], dtype=np.float32),
            names[1]: np.array([[3.0, 4.0], [0.0, 5.0]], dtype=np.float32),
        }
        K = {name: np.eye(3, dtype=np.float32) for name in names}
        w2c = {name: np.eye(4, dtype=np.float32) for name in names}
        result = subject.semantic_manifest_provenance(names, depth, K, w2c)
        expected = [
            shared_contract.canonical_frame_semantic_sha256(
                name,
                np.isfinite(depth[name]) & (depth[name] > 0),
                depth[name],
                K[name],
                w2c[name],
            )
            for name in names
        ]
        self.assertEqual(result["per_frame_semantic_sha256"], expected)
        self.assertEqual(
            result["semantic_manifest_sha256"],
            shared_contract.semantic_manifest_sha256(expected),
        )

    def test_depth_prep_sanitizes_only_invalid_mask_values_and_rgb_is_color_only(self):
        subject._DM_CACHE.clear()
        subject._DM_CACHE["a.jpg"] = np.array(
            [[1.0, np.nan], [np.inf, -1.0]], dtype=np.float32
        )
        with mock.patch.object(subject, "_load_rgb", return_value=np.zeros((2, 2, 3), np.uint8)):
            _, depth, _, fraction = subject._tsdf_prep_one("a.jpg")
        np.testing.assert_array_equal(depth, np.array([[1.0, 0.0], [0.0, 0.0]], np.float32))
        self.assertEqual(fraction, 0.25)

    def test_depth_truncation_crops_no_finite_positive_value(self):
        depth = np.array([[0.0, 1.0], [np.nan, 2.5]], dtype=np.float32)
        truncation = subject.safe_depth_truncation(depth)
        self.assertGreater(truncation, 2.5)
        with self.assertRaises(subject.ContractError):
            subject.safe_depth_truncation(np.zeros((2, 2), dtype=np.float32))

    def test_3x4_pose_is_expanded_without_transform(self):
        pose = np.arange(12, dtype=np.float64).reshape(3, 4)
        result = subject._as_open3d_extrinsic(pose)
        np.testing.assert_array_equal(result[:3], pose)
        np.testing.assert_array_equal(result[3], [0, 0, 0, 1])


class MeshOutputTests(unittest.TestCase):
    @staticmethod
    def mesh(vertices=None, triangles=None):
        vertices = np.array(
            vertices if vertices is not None else [[0, 0, 1], [1, 0, 1], [0, 1, 1]],
            dtype=float,
        )
        triangles = np.array(
            triangles if triangles is not None else [[0, 1, 2]], dtype=np.int64
        )
        return SimpleNamespace(vertices=vertices, triangles=triangles)

    def test_mesh_validation_rejects_empty_nonfinite_and_bad_indices(self):
        bad = [
            self.mesh(vertices=[]),
            self.mesh(triangles=[]),
            self.mesh(vertices=[[0, 0, np.nan], [1, 0, 1], [0, 1, 1]]),
            self.mesh(triangles=[[0, 1, 3]]),
            self.mesh(triangles=[[-1, 1, 2]]),
        ]
        for mesh in bad:
            with self.subTest(mesh=mesh), self.assertRaises(subject.ContractError):
                subject.validate_mesh(mesh)

    def test_writer_writes_only_isolated_mesh_and_provenance_and_not_legacy(self):
        mesh = self.mesh()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "new"
            legacy = root / "legacy"
            legacy.mkdir()
            sentinel = legacy / "sentinel"
            sentinel.write_text("safe")

            def writer(path, unused_mesh, **kwargs):
                Path(path).write_bytes(b"ply")
                return True

            with mock.patch.object(subject.o3d.io, "write_triangle_mesh", side_effect=writer):
                subject.write_outputs(out, mesh, {"contract": "test"})
            self.assertEqual({path.name for path in out.iterdir()}, {"mesh.ply", "provenance.json"})
            self.assertEqual(sentinel.read_text(), "safe")

    def test_output_validation_rejects_existing_and_protected_paths_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            protected = root / "legacy"
            protected.mkdir()
            existing = root / "existing"
            existing.mkdir()
            for candidate in (existing, protected / "child"):
                with self.subTest(candidate=candidate), self.assertRaises(subject.ContractError):
                    subject.validate_output_dir(candidate, [protected])
            self.assertFalse((protected / "child").exists())

    def test_complete_optimized_sfm_route_keeps_pose_and_uses_physical_6mm(self):
        class FakeMesh:
            vertices = np.array([[0, 0, 1], [1, 0, 1], [0, 1, 1]], dtype=float)
            triangles = np.array([[0, 1, 2]], dtype=np.int64)

            def compute_vertex_normals(self):
                return self

        class FakeVolume:
            def __init__(self):
                self.integrations = []

            def integrate(self, rgbd, camera, extrinsic):
                self.integrations.append((rgbd, camera, np.asarray(extrinsic).copy()))

            def extract_triangle_mesh(self):
                return FakeMesh()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scale = 1.007804831494465
            args, _, _ = make_fixture(
                root,
                coordinate_frame="optimized_sfm_cv",
                metres_per_model_unit=scale,
                valid_images=True,
            )
            volume = FakeVolume()

            def writer(path, unused_mesh, **kwargs):
                Path(path).write_bytes(b"ply")
                return True

            with (
                mock.patch.object(
                    subject.o3d.pipelines.integration,
                    "ScalableTSDFVolume",
                    return_value=volume,
                ) as volume_ctor,
                mock.patch.object(subject.o3d.geometry, "Image", side_effect=lambda value: value),
                mock.patch.object(
                    subject.o3d.geometry.RGBDImage,
                    "create_from_color_and_depth",
                    return_value="rgbd",
                ),
                mock.patch.object(
                    subject.o3d.camera, "PinholeCameraIntrinsic", return_value="camera"
                ),
                mock.patch.object(subject.o3d.io, "write_triangle_mesh", side_effect=writer),
            ):
                subject._run(args)

            self.assertEqual(len(volume.integrations), 2)
            np.testing.assert_array_equal(volume.integrations[0][2], np.eye(4))
            self.assertEqual(
                volume_ctor.call_args.kwargs["voxel_length"], 0.006 / scale
            )
            self.assertEqual(
                volume_ctor.call_args.kwargs["sdf_trunc"], 0.024 / scale
            )
            provenance = json.loads((args.out / "provenance.json").read_text())
            self.assertEqual(provenance["coordinate_frame"], "optimized_sfm_cv")
            self.assertEqual(provenance["metres_per_model_unit"], scale)
            self.assertFalse(provenance["coordinate_transform"]["transform_applied_by_route"])
            self.assertEqual(
                provenance["frozen_input_identity_contract"]["sha256"],
                sha(args.input_contract),
            )
            self.assertEqual(provenance["tsdf"]["physical_voxel_mm"], 6.0)


if __name__ == "__main__":
    unittest.main()
