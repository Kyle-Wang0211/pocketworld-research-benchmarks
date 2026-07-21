from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PYTHON_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_TOOLS))

import b0_export_alicevision as exporter
import b0_input_contract as contract


class AliceVisionExporterTests(unittest.TestCase):
    def test_ordered_name_hash_encoding_includes_final_lf_and_allows_empty(self) -> None:
        self.assertEqual(
            exporter.ordered_names_sha256(["a.jpg", "b.jpg"]),
            hashlib.sha256(b"a.jpg\nb.jpg\n").hexdigest(),
        )
        self.assertEqual(
            exporter.ordered_names_sha256([]), hashlib.sha256(b"").hexdigest()
        )

    def test_frozen_sim3_canonical_hash_matches_provenance(self) -> None:
        sim3 = exporter.FROZEN_SIM3
        values = np.asarray(
            [
                sim3["scale"],
                *np.asarray(sim3["rotation_row_major"]).reshape(-1).tolist(),
                *sim3["translation"],
            ],
            dtype="<f8",
        )
        self.assertEqual(
            hashlib.sha256(values.tobytes(order="C")).hexdigest(),
            sim3["canonical_sha256"],
        )

    def make_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        frames = np.array(["b.jpg", "a.jpg", "c.jpg"])
        depth = np.array(
            [
                [[1.0, 2.0], [0.0, 4.0]],
                [[2.0, 2.0], [2.0, 2.0]],
                [[3.0, 3.0], [3.0, np.nan]],
            ],
            dtype=np.float32,
        )
        dmcache = root / "dmcache.npz"
        np.savez_compressed(dmcache, frames=frames, dm=depth, sig=np.array("frozen-sig"))

        model_names = np.array(["c.jpg", "b.jpg", "a.jpg"])
        K = np.stack(
            [
                np.array([[20.0, 0.0, 0.9], [0.0, 21.0, 1.1], [0.0, 0.0, 1.0]], np.float32),
                np.array([[10.0, 0.0, 0.6], [0.0, 11.0, 0.4], [0.0, 0.0, 1.0]], np.float32),
                np.array([[15.0, 0.0, 1.0], [0.0, 16.0, 1.0], [0.0, 0.0, 1.0]], np.float32),
            ]
        )
        w2c = np.repeat(np.eye(4, dtype=np.float32)[None], 3, axis=0)
        w2c[1, :3, :3] = np.array(
            [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            np.float32,
        )
        w2c[1, :3, 3] = np.array([1.0, 2.0, 3.0], np.float32)
        model = root / "trio_model_lapa.npz"
        np.savez_compressed(model, names=model_names, K=K, w2c=w2c)

        frame_list = root / "reconstruction.json"
        frame_list.write_text(json.dumps(["b.jpg", "c.jpg"]), encoding="utf-8")
        image_root = root / "images"
        image_root.mkdir()
        for name in frames:
            (image_root / str(name)).write_bytes(b"not-read-by-meshing")
        return dmcache, model, frame_list, image_root

    def write_unified_contract(
        self,
        root: Path,
        dmcache: Path,
        model: Path,
        frame_list: Path,
        image_root: Path,
    ) -> Path:
        with np.load(dmcache, allow_pickle=False) as archive:
            dm_names = [str(value) for value in archive["frames"].tolist()]
            depth = archive["dm"]
            signature = str(np.asarray(archive["sig"]).item())
        with np.load(model, allow_pickle=False) as archive:
            model_names = [str(value) for value in archive["names"].tolist()]
        reconstruction = contract.parse_frame_list(frame_list)
        heldout = [name for name in dm_names if name not in reconstruction]
        by_name = {
            name: {
                "sha256": contract.sha256_file(image_root / name),
                "size_bytes": (image_root / name).stat().st_size,
            }
            for name in dm_names
        }
        payload = {
            "schema_version": exporter.INPUT_IDENTITY_CONTRACT_SCHEMA,
            "dataset_id": "unit-fixture-non-trio",
            "coordinate_frame": "raw_lapa_model",
            "metres_per_model_unit": exporter.FROZEN_SIM3["scale"],
            "transductive_policy": {
                "present": True,
                "route_allowed": True,
                "quality_scoring_forbidden": False,
            },
            "dmcache": {
                "sha256": contract.sha256_file(dmcache),
                "signature": signature,
                "depth": {"shape": list(depth.shape), "dtype": str(depth.dtype)},
                "frame_order": dm_names,
                "frame_order_sha256": exporter.ordered_names_sha256(dm_names),
            },
            "model_cache": {
                "sha256": contract.sha256_file(model),
                "frame_order": model_names,
                "frame_order_sha256": exporter.ordered_names_sha256(model_names),
            },
            "splits": {
                "fixture": {
                    "reconstruction": {
                        "frames": reconstruction,
                        "file_sha256": contract.sha256_file(frame_list),
                        "semantic_sha256": exporter.ordered_names_sha256(
                            reconstruction
                        ),
                    },
                    "heldout": {
                        "frames": heldout,
                        "file_sha256": exporter.ordered_names_sha256(heldout),
                        "semantic_sha256": exporter.ordered_names_sha256(heldout),
                    },
                }
            },
            "images": {
                "root_manifest_sha256": exporter.image_root_manifest_sha256(
                    dm_names, by_name
                ),
                "by_name": by_name,
            },
        }
        path = root / "input-contract.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def test_exports_joined_lapa_inputs_neutral_similarity_and_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            output = root / "new-output"
            captured: dict[str, tuple[np.ndarray, int]] = {}

            def fake_write(path: Path, pixels: np.ndarray, *, depth_values: int) -> None:
                captured[path.name] = (pixels.copy(), depth_values)
                path.write_bytes(b"fake-exr")

            def fake_read(path: Path) -> np.ndarray:
                return captured[path.name][0].copy()

            provenance = exporter.export_alicevision(
                dmcache_path=dmcache,
                model_cache_path=model,
                frame_list_path=frame_list,
                image_paths=exporter.image_paths_from_root(image_root, ["b.jpg", "c.jpg"]),
                output=output,
                expected_dmcache_sha256=contract.sha256_file(dmcache),
                expected_signature="frozen-sig",
                expected_model_cache_sha256=contract.sha256_file(model),
                exr_writer=fake_write,
                exr_reader=fake_read,
                image_root=image_root,
            )

            scene = json.loads((output / "scene.sfm").read_text(encoding="utf-8"))
            self.assertEqual([v["path"] for v in scene["views"]], [
                str((image_root / "b.jpg").resolve()),
                str((image_root / "c.jpg").resolve()),
            ])
            # b.jpg is index 1 in the model cache: K cx/cy = .6/.4, W/H = 2/2.
            self.assertAlmostEqual(
                float(scene["intrinsics"][0]["principalPoint"][0]), -0.4, places=6
            )
            self.assertAlmostEqual(
                float(scene["intrinsics"][0]["principalPoint"][1]), -0.6, places=6
            )
            self.assertEqual(
                scene["poses"][0]["pose"]["transform"]["center"],
                ["-2.0", "1.0", "-3.0"],
            )
            self.assertEqual(scene["poses"][0]["pose"]["transform"]["rotation"], [
                "0.0", "1.0", "0.0", "-1.0", "0.0", "0.0", "0.0", "0.0", "1.0"
            ])
            self.assertTrue(np.all(captured["1000_simMap.exr"][0] == -1.0))
            self.assertIn("1002_depthMap.exr", captured)
            self.assertNotIn("1001_depthMap.exr", captured)
            # Sparse b.jpg mask has three valid depth samples, not H*W=4.
            self.assertEqual(captured["1000_depthMap.exr"][1], 3)
            self.assertEqual(captured["1000_simMap.exr"][1], 3)
            self.assertNotEqual(captured["1000_depthMap.exr"][1], 4)
            self.assertEqual(captured["1000_depthMap.exr"][0][1, 0], 0.0)
            self.assertEqual(provenance["frame_count"], 2)
            self.assertEqual(provenance["coordinate_frame"], "raw_lapa_model")
            self.assertFalse(
                provenance["frozen_sim3_model_to_arkit"]["applied_by_adapter"]
            )
            self.assertEqual(len(provenance["per_frame_semantic_sha256"]), 2)
            self.assertEqual(
                provenance["input_equivalence_contract"]["mask_semantics"],
                "isfinite(dm) & (dm > 0)",
            )
            self.assertEqual(
                provenance["input_equivalence_contract"][
                    "semantic_manifest_sha256"
                ],
                provenance["semantic_manifest_sha256"],
            )
            self.assertEqual(
                provenance["semantic_hash_schema"]["version"],
                contract.SEMANTIC_HASH_VERSION,
            )
            self.assertTrue((output / "provenance.json").is_file())
            self.assertEqual(
                provenance["image_source"]["root_path"],
                str(image_root.resolve()),
            )
            self.assertEqual(
                [row["frame"] for row in provenance["image_source"]["frames"]],
                ["b.jpg", "c.jpg"],
            )
            self.assertTrue(
                all(len(row["sha256"]) == 64 for row in provenance["image_source"]["frames"])
            )
            self.assertLessEqual(
                provenance["max_serialized_z_ray_z_relative_roundtrip_error"],
                exporter.ROUNDTRIP_RELATIVE_ERROR_LIMIT,
            )

    def test_existing_output_and_wrong_frozen_cache_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            output = root / "already-there"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                exporter.export_alicevision(
                    dmcache_path=dmcache,
                    model_cache_path=model,
                    frame_list_path=frame_list,
                    image_paths=exporter.image_paths_from_root(image_root, ["b.jpg", "c.jpg"]),
                    output=output,
                    expected_dmcache_sha256=contract.sha256_file(dmcache),
                    expected_signature="frozen-sig",
                    expected_model_cache_sha256=contract.sha256_file(model),
                    exr_writer=lambda *_args, **_kwargs: None,
                )
            with self.assertRaisesRegex(
                contract.RouteInputNotEquivalent,
                r"^ROUTE_INPUT_NOT_EQUIVALENT$",
            ):
                exporter.export_alicevision(
                    dmcache_path=dmcache,
                    model_cache_path=model,
                    frame_list_path=frame_list,
                    image_paths=exporter.image_paths_from_root(image_root, ["b.jpg", "c.jpg"]),
                    output=root / "new-output",
                    expected_dmcache_sha256="0" * 64,
                    expected_signature="frozen-sig",
                    expected_model_cache_sha256=contract.sha256_file(model),
                    exr_writer=lambda *_args, **_kwargs: None,
                )

    def test_brand_new_absolute_run_root_is_created_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            output = root / "brand-new-run" / "fusecut" / "export"
            self.assertFalse(output.parent.parent.exists())
            contract_path = self.write_unified_contract(
                root, dmcache, model, frame_list, image_root
            )

            result = exporter.main(
                [
                    "--dmcache", str(dmcache),
                    "--model-cache", str(model),
                    "--frame-list", str(frame_list),
                    "--image-root", str(image_root),
                    "--input-contract", str(contract_path),
                    "--split-id", "fixture",
                    "--out", str(output),
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue((output / "scene.sfm").is_file())
            self.assertTrue((output / "provenance.json").is_file())

    def test_output_and_parent_symlinks_are_rejected_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            kwargs = {
                "dmcache_path": dmcache,
                "model_cache_path": model,
                "frame_list_path": frame_list,
                "image_paths": exporter.image_paths_from_root(
                    image_root, ["b.jpg", "c.jpg"]
                ),
                "expected_dmcache_sha256": contract.sha256_file(dmcache),
                "expected_signature": "frozen-sig",
                "expected_model_cache_sha256": contract.sha256_file(model),
                "exr_writer": lambda *_args, **_kwargs: None,
            }

            dangling_target = root / "must-not-be-created"
            output_link = root / "output-link"
            output_link.symlink_to(dangling_target, target_is_directory=True)
            with self.assertRaises(FileExistsError):
                exporter.export_alicevision(output=output_link, **kwargs)
            self.assertFalse(dangling_target.exists())

            real_parent = root / "real-parent"
            real_parent.mkdir()
            parent_link = root / "parent-link"
            parent_link.symlink_to(real_parent, target_is_directory=True)
            linked_output = parent_link / "fusecut" / "export"
            with self.assertRaises(OSError):
                exporter.export_alicevision(output=linked_output, **kwargs)
            self.assertFalse((real_parent / "fusecut").exists())

            file_parent = root / "not-a-directory"
            file_parent.write_bytes(b"file")
            with self.assertRaises(OSError):
                exporter.export_alicevision(
                    output=file_parent / "fusecut" / "export", **kwargs
                )

    def test_relative_output_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            with self.assertRaisesRegex(ValueError, "absolute"):
                exporter.export_alicevision(
                    dmcache_path=dmcache,
                    model_cache_path=model,
                    frame_list_path=frame_list,
                    image_paths=exporter.image_paths_from_root(
                        image_root, ["b.jpg", "c.jpg"]
                    ),
                    output=Path("relative") / "fusecut" / "export",
                    expected_dmcache_sha256=contract.sha256_file(dmcache),
                    expected_signature="frozen-sig",
                    expected_model_cache_sha256=contract.sha256_file(model),
                    exr_writer=lambda *_args, **_kwargs: None,
                )

    def test_manifest_relative_jpeg_path_uses_explicit_capture_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            capture = root / "capture"
            photos = capture / "photos_highres"
            photos.mkdir(parents=True)
            wanted = photos / "a.jpg"
            wanted.write_bytes(b"jpeg")
            diagnostics = root / "diagnostics" / "deep"
            diagnostics.mkdir(parents=True)
            manifest = diagnostics / "manifest.json"
            manifest.write_text(
                json.dumps([{"jpegPath": "photos_highres/a.jpg"}]),
                encoding="utf-8",
            )

            mapping = exporter.image_paths_from_manifest(
                manifest, ["a.jpg"], image_root=capture
            )
            self.assertEqual(mapping, {"a.jpg": wanted.resolve()})

    def test_manifest_can_use_photo_directory_as_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            photos = root / "photos_highres"
            photos.mkdir()
            wanted = photos / "a.jpg"
            wanted.write_bytes(b"jpeg")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps([{"jpegPath": "photos_highres/a.jpg"}]),
                encoding="utf-8",
            )

            mapping = exporter.image_paths_from_manifest(
                manifest, ["a.jpg"], image_root=photos
            )
            self.assertEqual(mapping, {"a.jpg": wanted.resolve()})

    def test_cli_requires_explicit_image_root_even_with_manifest(self) -> None:
        with self.assertRaises(SystemExit):
            exporter.parse_args(
                [
                    "--dmcache", "dm.npz",
                    "--model-cache", "model.npz",
                    "--frame-list", "frames.json",
                    "--manifest", "manifest.json",
                    "--out", "out",
                ]
            )

    def test_python311_real_float32_exr_roundtrip_and_alicevision_metadata(self) -> None:
        self.assertEqual(os.environ.get("OPENCV_IO_ENABLE_OPENEXR"), "1")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depth.exr"
            expected = np.array(
                [[0.0, 1.0, 2.5], [3.25, 1.0e-4, 500.0]], dtype=np.float32
            )
            diagnostics = exporter.write_typed_exr(
                path, expected, depth_values=5
            )
            actual = exporter.read_float_exr(path)

            self.assertEqual(actual.dtype, np.float32)
            np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=0.0)
            self.assertEqual(diagnostics["writer_backend"], "OpenEXR.File")
            self.assertEqual(diagnostics["readback_backend"], "cv2.imread")
            self.assertTrue(
                diagnostics["opencv_backend"]["float32_writer_verified"]
            )
            self.assertEqual(
                diagnostics["writer_selection_reason"],
                "OpenCV_cannot_emit_typed_AliceVision_attributes",
            )
            self.assertLessEqual(
                diagnostics["max_float32_serialization_relative_error"], 1e-6
            )

            import OpenEXR

            header = OpenEXR.File(str(path), separate_channels=True).header()
            self.assertEqual(header["AliceVision:downscale"], 1)
            self.assertEqual(header["AliceVision:nbDepthValues"], 5)

    def test_unified_frozen_contract_drives_export_and_detects_image_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            requested = ["b.jpg", "c.jpg"]
            image_paths = exporter.image_paths_from_root(image_root, requested)
            contract_path = self.write_unified_contract(
                root, dmcache, model, frame_list, image_root
            )
            frozen = exporter.load_input_identity_contract(contract_path)
            self.assertEqual(frozen["schema_version"], "b0-input-contract-v1")
            self.assertNotEqual(
                frozen["dmcache"]["sha256"], exporter.EXPECTED_DMCACHE_SHA256
            )

            captured: dict[str, np.ndarray] = {}

            def fake_write(path: Path, pixels: np.ndarray, **_kwargs: object) -> None:
                captured[path.name] = pixels.copy()
                path.write_bytes(b"fake")

            provenance = exporter.export_alicevision(
                dmcache_path=dmcache,
                model_cache_path=model,
                frame_list_path=frame_list,
                image_paths=image_paths,
                output=root / "export",
                exr_writer=fake_write,
                exr_reader=lambda path: captured[path.name].copy(),
                image_root=image_root,
                universe_image_paths=exporter.image_paths_from_root(
                    image_root, ["b.jpg", "a.jpg", "c.jpg"]
                ),
                input_contract_path=contract_path,
                split_id="fixture",
            )
            self.assertEqual(
                provenance["frozen_input_identity_contract"]["sha256"],
                contract.sha256_file(contract_path),
            )

            # a.jpg is held out, so this proves the whole image universe is
            # validated even though only b.jpg/c.jpg are exported.
            (image_root / "a.jpg").write_bytes(b"mutated-heldout")
            rejected_output = root / "rejected"
            with self.assertRaisesRegex(
                contract.RouteInputNotEquivalent,
                r"^ROUTE_INPUT_NOT_EQUIVALENT$",
            ):
                exporter.export_alicevision(
                    dmcache_path=dmcache,
                    model_cache_path=model,
                    frame_list_path=frame_list,
                    image_paths=image_paths,
                    output=rejected_output,
                    exr_writer=fake_write,
                    exr_reader=lambda path: captured[path.name].copy(),
                    image_root=image_root,
                    universe_image_paths=exporter.image_paths_from_root(
                        image_root, ["b.jpg", "a.jpg", "c.jpg"]
                    ),
                    input_contract_path=contract_path,
                    split_id="fixture",
                )
            self.assertFalse(rejected_output.exists())

    def test_no_contract_and_no_explicit_expected_identities_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            with self.assertRaisesRegex(
                contract.RouteInputNotEquivalent,
                r"^ROUTE_INPUT_NOT_EQUIVALENT$",
            ):
                exporter.export_alicevision(
                    dmcache_path=dmcache,
                    model_cache_path=model,
                    frame_list_path=frame_list,
                    image_paths=exporter.image_paths_from_root(
                        image_root, ["b.jpg", "c.jpg"]
                    ),
                    output=root / "must-not-exist",
                )

    def test_unified_contract_rejects_each_route_identity_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            requested = ["b.jpg", "c.jpg"]
            image_paths = exporter.image_paths_from_root(image_root, requested)
            universe_image_paths = exporter.image_paths_from_root(
                image_root, ["b.jpg", "a.jpg", "c.jpg"]
            )
            base_path = self.write_unified_contract(
                root, dmcache, model, frame_list, image_root
            )
            base = json.loads(base_path.read_text(encoding="utf-8"))

            def replace_dm_sha(payload: dict[str, object]) -> None:
                payload["dmcache"]["sha256"] = "0" * 64

            def replace_dm_signature(payload: dict[str, object]) -> None:
                payload["dmcache"]["signature"] = "other"

            def replace_depth_shape(payload: dict[str, object]) -> None:
                payload["dmcache"]["depth"]["shape"] = [99, 2, 2]

            def replace_dm_order(payload: dict[str, object]) -> None:
                payload["dmcache"]["frame_order"] = list(
                    reversed(payload["dmcache"]["frame_order"])
                )

            def replace_model_sha(payload: dict[str, object]) -> None:
                payload["model_cache"]["sha256"] = "0" * 64

            def replace_model_order_sha(payload: dict[str, object]) -> None:
                payload["model_cache"]["frame_order_sha256"] = "0" * 64

            def replace_reconstruction_frames(payload: dict[str, object]) -> None:
                split = payload["splits"]["fixture"]["reconstruction"]
                split["frames"] = list(reversed(split["frames"]))

            def replace_list_file_sha(payload: dict[str, object]) -> None:
                payload["splits"]["fixture"]["reconstruction"][
                    "file_sha256"
                ] = "0" * 64

            def replace_list_semantic_sha(payload: dict[str, object]) -> None:
                payload["splits"]["fixture"]["reconstruction"][
                    "semantic_sha256"
                ] = "0" * 64

            def replace_image_manifest_sha(payload: dict[str, object]) -> None:
                payload["images"]["root_manifest_sha256"] = "0" * 64

            def replace_image_sha(payload: dict[str, object]) -> None:
                payload["images"]["by_name"]["b.jpg"]["sha256"] = "0" * 64

            def replace_raw_scale(payload: dict[str, object]) -> None:
                payload["metres_per_model_unit"] = 1.0

            mutations = {
                "dm_sha": replace_dm_sha,
                "dm_signature": replace_dm_signature,
                "depth_shape": replace_depth_shape,
                "dm_order": replace_dm_order,
                "model_sha": replace_model_sha,
                "model_order_sha": replace_model_order_sha,
                "reconstruction_frames": replace_reconstruction_frames,
                "list_file_sha": replace_list_file_sha,
                "list_semantic_sha": replace_list_semantic_sha,
                "image_manifest_sha": replace_image_manifest_sha,
                "image_sha": replace_image_sha,
                "raw_scale": replace_raw_scale,
            }
            for index, (name, mutate) in enumerate(mutations.items()):
                payload = copy.deepcopy(base)
                mutate(payload)
                contract_path = root / f"bad-contract-{index}.json"
                contract_path.write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                )
                output = root / f"bad-output-{index}"
                with self.subTest(identity=name), self.assertRaisesRegex(
                    contract.RouteInputNotEquivalent,
                    r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                ):
                    exporter.export_alicevision(
                        dmcache_path=dmcache,
                        model_cache_path=model,
                        frame_list_path=frame_list,
                        image_paths=image_paths,
                        universe_image_paths=universe_image_paths,
                        output=output,
                        image_root=image_root,
                        input_contract_path=contract_path,
                        split_id="fixture",
                    )
                self.assertFalse(output.exists())

    def test_coordinate_frame_scale_acceptance_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            dmcache, model, frame_list, image_root = self.make_fixture(root)
            requested = ["b.jpg", "c.jpg"]
            route_images = exporter.image_paths_from_root(image_root, requested)
            universe_images = exporter.image_paths_from_root(
                image_root, ["b.jpg", "a.jpg", "c.jpg"]
            )
            base_path = self.write_unified_contract(
                root, dmcache, model, frame_list, image_root
            )
            base = json.loads(base_path.read_text(encoding="utf-8"))

            captured: dict[str, np.ndarray] = {}

            def fake_write(path: Path, pixels: np.ndarray, **_kwargs: object) -> None:
                captured[path.name] = pixels.copy()
                path.write_bytes(b"fake")

            cases = [
                ("metric_arkit_cv", 1.0, True),
                ("metric_arkit_cv", 1.0001, False),
                ("raw_lapa_model", exporter.FROZEN_SIM3["scale"], True),
                ("raw_lapa_model", 0.2, False),
                ("optimized_sfm_cv", 1.007804831494465, True),
                ("optimized_sfm_cv", 0.0, False),
            ]
            for index, (coordinate_frame, scale, accepted) in enumerate(cases):
                payload = copy.deepcopy(base)
                payload["coordinate_frame"] = coordinate_frame
                payload["metres_per_model_unit"] = scale
                contract_path = root / f"coordinate-{index}.json"
                contract_path.write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                )
                kwargs = {
                    "dmcache_path": dmcache,
                    "model_cache_path": model,
                    "frame_list_path": frame_list,
                    "image_paths": route_images,
                    "universe_image_paths": universe_images,
                    "output": root / f"coordinate-output-{index}",
                    "exr_writer": fake_write,
                    "exr_reader": lambda path: captured[path.name].copy(),
                    "image_root": image_root,
                    "input_contract_path": contract_path,
                    "split_id": "fixture",
                }
                if accepted:
                    provenance = exporter.export_alicevision(**kwargs)
                    self.assertEqual(provenance["coordinate_frame"], coordinate_frame)
                    self.assertEqual(provenance["metres_per_model_unit"], scale)
                else:
                    with self.assertRaisesRegex(
                        contract.RouteInputNotEquivalent,
                        r"^ROUTE_INPUT_NOT_EQUIVALENT$",
                    ):
                        exporter.export_alicevision(**kwargs)

    def test_cli_requires_contract_and_split(self) -> None:
        common = [
            "--dmcache", "dm.npz",
            "--model-cache", "model.npz",
            "--frame-list", "frames.json",
            "--image-root", "images",
        ]
        with self.assertRaises(SystemExit):
            exporter.parse_args([*common, "--out", "out"])
        parsed = exporter.parse_args(
            [
                *common,
                "--input-contract", "contract.json",
                "--split-id", "fixture",
                "--out", "out",
            ]
        )
        self.assertEqual(parsed.input_contract, Path("contract.json"))
        self.assertEqual(parsed.split_id, "fixture")


if __name__ == "__main__":
    unittest.main()
