from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_TOOLS))

import b0_preregister as prereg
import b0_input_contract as shared_contract


def _list_bytes(names: list[str]) -> bytes:
    return ("\n".join(names) + "\n").encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class SplitPolicyTests(unittest.TestCase):
    def test_cap_split_uses_frozen_local_phase(self) -> None:
        frames = [f"frame_{i:03d}.jpg" for i in range(100)]
        reconstruction, heldout = prereg.split_cap100(frames)

        self.assertEqual(heldout, [frames[i] for i in range(4, 95, 5)])
        self.assertEqual(len(heldout), 19)
        self.assertEqual(len(reconstruction), 81)
        self.assertEqual(set(reconstruction) | set(heldout), set(frames))
        self.assertFalse(set(reconstruction) & set(heldout))

    def test_full_split_uses_historical_dmcache_phase(self) -> None:
        all_frames = [f"frame_{i:03d}.jpg" for i in range(413)]
        reconstruction, heldout = prereg.split_full413(all_frames)

        expected_indices = list(range(4, 413, 5))
        self.assertEqual(heldout, [all_frames[index] for index in expected_indices])
        self.assertEqual((len(reconstruction), len(heldout)), (331, 82))
        self.assertEqual(
            reconstruction,
            [name for index, name in enumerate(all_frames) if index not in expected_indices],
        )
        self.assertEqual(set(reconstruction) | set(heldout), set(all_frames))
        self.assertFalse(set(reconstruction) & set(heldout))

    def test_frame_list_hash_is_newline_terminated_sha256(self) -> None:
        names = ["a.jpg", "b.jpg"]
        self.assertEqual(prereg.hash_frame_list(names), _sha(b"a.jpg\nb.jpg\n"))


class FrozenRegistrationTests(unittest.TestCase):
    def _make_fixture(self, root: Path) -> dict[str, object]:
        all_frames = [f"frame_{i:03d}.jpg" for i in range(413)]
        cap_frames = all_frames[:100]

        dmcache = root / "dmcache.npz"
        dm = np.ones((413, 2, 3), dtype=np.float32)
        dm[:, 0, 0] = 0.0
        np.savez(
            dmcache,
            frames=np.asarray(all_frames),
            dm=dm,
            sig=np.asarray("fixture-signature"),
        )

        model_cache = root / "model.npz"
        K = np.repeat(np.eye(3, dtype=np.float32)[None, :, :], 413, axis=0)
        K[:, 0, 0] = 500.0
        K[:, 1, 1] = 500.0
        w2c = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], 413, axis=0)
        centers = np.zeros((413, 3), dtype=np.float64)
        # Deliberately reverse model order: joining must be by exact basename,
        # never by incidental array index.
        reverse = np.arange(412, -1, -1)
        np.savez(
            model_cache,
            names=np.asarray(all_frames)[reverse],
            K=K[reverse],
            w2c=w2c[reverse],
            centers=centers[reverse],
            obs_idx=np.empty((0,), dtype=np.int64),
            obs_off=np.zeros((414,), dtype=np.int64),
            pts=np.empty((0, 3), dtype=np.float64),
        )

        trio_refs = root / "trio_refs.json"
        trio_refs.write_text(
            json.dumps({"pool": all_frames, "refs": all_frames}), encoding="utf-8"
        )

        cap_list = root / "image_list_100.txt"
        cap_list.write_bytes(_list_bytes(cap_frames))

        spatial_manifest = root / "k414_spatial_order_manifest.json"
        spatial_manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": "fixture",
                    "frames": [
                        {"jpegPath": f"photos_highres/{name}"}
                        for name in all_frames + ["unregistered.jpg"]
                    ],
                    "spatialOrder": list(range(414)),
                }
            ),
            encoding="utf-8",
        )

        cap_reconstruction, cap_heldout = prereg.split_cap100(cap_frames)
        full_reconstruction, full_heldout = prereg.split_full413(all_frames)
        code_root = root / "code"
        for relative_path in prereg.FROZEN_CODE_RELATIVE_PATHS:
            script = code_root / relative_path
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                f"# frozen fixture for {relative_path}\n", encoding="utf-8"
            )
        alicevision_binary = root / "aliceVision_meshing"
        alicevision_binary.write_bytes(b"fixture alicevision binary\n")
        alicevision_binary.chmod(0o755)
        return {
            "all_frames": all_frames,
            "cap_frames": cap_frames,
            "dmcache": dmcache,
            "model_cache": model_cache,
            "trio_refs": trio_refs,
            "cap_list": cap_list,
            "spatial_manifest": spatial_manifest,
            "code_root": code_root,
            "alicevision_binary": alicevision_binary,
            "patches": {
                "EXPECTED_DMCACHE_SHA256": prereg.sha256_file(dmcache),
                "EXPECTED_MODEL_CACHE_SHA256": prereg.sha256_file(model_cache),
                "EXPECTED_TRIO_REFS_SHA256": prereg.sha256_file(trio_refs),
                "EXPECTED_CAP_LIST_SHA256": prereg.sha256_file(cap_list),
                "EXPECTED_SPATIAL_MANIFEST_SHA256": prereg.sha256_file(spatial_manifest),
                "EXPECTED_DEPTH_SHAPE": (413, 2, 3),
                "EXPECTED_DMCACHE_SIGNATURE": "fixture-signature",
                "EXPECTED_CAP_HELDOUT_SHA256": prereg.hash_frame_list(cap_heldout),
                "EXPECTED_CAP_RECONSTRUCTION_SHA256": prereg.hash_frame_list(
                    cap_reconstruction
                ),
                "EXPECTED_FULL_ALL_SHA256": prereg.hash_frame_list(all_frames),
                "EXPECTED_FULL_HELDOUT_SHA256": prereg.hash_frame_list(full_heldout),
                "EXPECTED_FULL_RECONSTRUCTION_SHA256": prereg.hash_frame_list(
                    full_reconstruction
                ),
            },
        }

    def _run_fixture(self, fixture: dict[str, object], out: Path) -> dict[str, object]:
        patches = fixture["patches"]
        with mock.patch.multiple(prereg, **patches):
            return prereg.preregister(
                dmcache=fixture["dmcache"],
                trio_model_lapa=fixture["model_cache"],
                trio_refs=fixture["trio_refs"],
                cap100_list=fixture["cap_list"],
                spatial_manifest=fixture["spatial_manifest"],
                code_root=fixture["code_root"],
                alicevision_binary=fixture["alicevision_binary"],
                out=out,
            )

    def test_writes_isolated_contract_lists_and_hashed_input_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            out = root / "registration"

            result = self._run_fixture(fixture, out)

            self.assertEqual(result["status"], "FROZEN")
            expected_files = {
                "contract.json",
                "contract.sha256",
                "input_manifest.json",
                "input_manifest.sha256",
                "lists/cap100_all.txt",
                "lists/cap100_heldout.txt",
                "lists/cap100_reconstruction.txt",
                "lists/full413_all.txt",
                "lists/full413_heldout.txt",
                "lists/full413_reconstruction.txt",
            }
            self.assertEqual(
                {str(path.relative_to(out)) for path in out.rglob("*") if path.is_file()},
                expected_files,
            )
            self.assertEqual(
                (out / "lists/cap100_all.txt").read_bytes(),
                fixture["cap_list"].read_bytes(),
            )

            manifest = json.loads((out / "input_manifest.json").read_text())
            self.assertTrue(manifest["joins"]["dmcache_model_exact_name_set"])
            self.assertTrue(manifest["spatial_manifest"]["exact_cap100_match"])
            self.assertEqual(manifest["splits"]["cap100"]["reconstruction"]["count"], 81)
            self.assertEqual(manifest["splits"]["cap100"]["heldout"]["count"], 19)
            self.assertEqual(
                manifest["splits"]["full413_quality"]["reconstruction"]["count"],
                331,
            )
            self.assertEqual(
                manifest["splits"]["full413_quality"]["heldout"]["count"], 82
            )
            self.assertEqual(
                manifest["splits"]["full413_quality"]["heldout_global_indices"],
                list(range(4, 413, 5)),
            )
            self.assertEqual(manifest["trio_refs"]["arrays"]["refs"]["count"], 413)
            manifest_digest = prereg.sha256_file(out / "input_manifest.json")
            self.assertEqual(
                (out / "input_manifest.sha256").read_text(),
                f"{manifest_digest}  input_manifest.json\n",
            )

            contract = json.loads((out / "contract.json").read_text())
            self.assertEqual(contract["only_experimental_variable"], "meshing_backend")
            self.assertEqual(
                contract["claim_scope"],
                "fusion-held-out transductive observation-consistency; "
                "cache had all frames upstream",
            )
            self.assertEqual(
                contract["frozen_authority"]["prompt_sha256"],
                "325855aceeee4abd46ddfaf2716f2ed9885956430eb5e2d392d25b4cc211e1a6",
            )
            self.assertEqual(
                contract["frozen_authority"]["code_head"],
                "9f8965808888f9e524cf37193de093195438b062",
            )
            source_state = contract["frozen_authority"]["source_state"]
            self.assertFalse(source_state["git_head_contains_experiment_code"])
            self.assertEqual(source_state["git_head"], prereg.FROZEN_CODE_HEAD)
            bundle = source_state["dirty_code_bundle"]
            self.assertEqual(
                [entry["relative_path"] for entry in bundle["files"]],
                list(prereg.FROZEN_CODE_RELATIVE_PATHS),
            )
            self.assertEqual(
                {entry["sha256"] for entry in bundle["files"]},
                {
                    prereg.sha256_file(
                        fixture["code_root"] / entry["relative_path"]
                    )
                    for entry in bundle["files"]
                },
            )
            self.assertEqual(len(bundle["bundle_sha256"]), 64)
            binary = contract["frozen_authority"]["alicevision_binary"]
            self.assertEqual(
                binary["sha256"], prereg.sha256_file(fixture["alicevision_binary"])
            )
            environment = contract["frozen_authority"]["environment_identity"]
            self.assertEqual(len(environment["sha256"]), 64)
            self.assertIn("python", environment["identity"])
            self.assertIn("host", environment["identity"])
            self.assertEqual(contract["random_seed"], 20260721)
            self.assertFalse(contract["preregistration_state"]["outputs_inspected"])
            self.assertEqual(
                contract["splits"]["full413_quality"]["reconstruction_count"], 331
            )
            self.assertEqual(
                contract["splits"]["full413_quality"]["heldout_count"], 82
            )
            self.assertEqual(
                contract["execution_plan"]["cap100_quality"]["output_subdir"],
                "runs/cap100_quality",
            )
            self.assertEqual(
                contract["execution_plan"]["full413_quality"]["output_subdir"],
                "runs/full413_quality",
            )
            run_policy = contract["run_repetition_policy"]
            self.assertEqual(run_policy["seed"], 20260721)
            self.assertEqual(
                run_policy["primary_selection"], "first successful run"
            )
            self.assertFalse(run_policy["best_of_n_allowed"])
            self.assertEqual(
                run_policy["execution_order"], ["TSDF primary", "FuseCut primary"]
            )
            self.assertTrue(run_policy["fresh_process_per_route"])
            self.assertTrue(run_policy["common_environment_required"])
            self.assertEqual(run_policy["tsdf"]["primary_runs"], 1)
            self.assertEqual(
                run_policy["cap100_fusecut"]["additional_diagnostic_repeats_max"],
                2,
            )
            self.assertEqual(
                run_policy["cap100_fusecut"]["repeat_use"],
                "nondeterminism diagnostic only",
            )
            self.assertFalse(
                run_policy["cap100_fusecut"]["may_replace_primary"]
            )
            self.assertEqual(
                run_policy["full413_quality"]["primary_selection"],
                "first successful fixed-seed run",
            )
            self.assertFalse(
                run_policy["full413_quality"]["output_based_selection_allowed"]
            )
            self.assertEqual(
                contract["prepared_masks"]["status"], "PENDING_PREPARE"
            )
            self.assertFalse(contract["prepared_masks"]["hash_fabricated"])
            self.assertNotIn("cap100_relaxed", contract["gates"])
            for profile in ("cap100_quality", "full413_quality"):
                gate = contract["gates"][profile]
                self.assertEqual(gate["coverage_delta_pp_min"], -2.0)
                self.assertEqual(gate["unsupported_gt_20mm_delta_pp_max"], 2.0)
                self.assertEqual(gate["median_absrel_delta_pp_max"], 0.5)
                self.assertEqual(gate["p95_absrel_delta_pp_max"], 2.0)
                self.assertEqual(gate["median_normal_error_delta_max_deg"], 2.0)
                self.assertEqual(gate["double_shell_rate_delta_pp_max"], 1.0)
                self.assertEqual(
                    gate["double_shell_p95_separation_delta_max_mm"], 5.0
                )
                self.assertEqual(gate["nonmanifold_edge_fraction_max"], 1e-4)

            claim = contract["improvement_claim"]
            self.assertEqual(claim["bootstrap_draws"], 10_000)
            self.assertEqual(claim["seed"], 20260721)
            self.assertTrue(claim["exact_draw_count_required"])

            commands = contract["execution_plan"]["commands_skeleton"]
            monitor = "tools/python/b0_run_monitored.py"
            for name in ("tsdf", "fusecut_export", "alicevision_meshing"):
                self.assertIn(monitor, commands[name])
                self.assertIn("--resource-log", commands[name])
                self.assertIn("--status", commands[name])
                self.assertIn("--peak-rss-gib", commands[name])
                self.assertIn("--swap-growth-gib", commands[name])
                self.assertIn("--wall-time-seconds", commands[name])

            meshing = commands["alicevision_meshing"]
            frozen_pairs = {
                "--output": "<FUSECUT_RUN>/dense.sfm",
                "--outputMesh": "<FUSECUT_RUN>/mesh.obj",
                "--partitioning": "singleBlock",
                "--repartition": "multiResolution",
                "--estimateSpaceFromSfM": "false",
                "--addLandmarksToTheDensePointCloud": "false",
                "--colorizeOutput": "false",
                "--minStep": "1",
                "--maxPointsPerVoxel": "6000000",
                "--minVis": "2",
                "--simFactor": "15",
                "--angleFactor": "15",
                "--universePercentile": "0.999",
                "--estimateSpaceMinObservations": "3",
                "--estimateSpaceMinObservationAngle": "10",
                "--pixSizeMarginInitCoef": "2",
                "--pixSizeMarginFinalCoef": "1",
                "--voteMarginFactor": "4",
                "--contributeMarginFactor": "2",
                "--simGaussianSizeInit": "10",
                "--simGaussianSize": "10",
                "--minAngleThreshold": "0.1",
                "--refineFuse": "true",
                "--helperPointsGridSize": "10",
                "--densifyNbFront": "0",
                "--densifyNbBack": "0",
                "--densifyScale": "1",
                "--maskHelperPointsWeight": "0",
                "--maskBorderSize": "1",
                "--nPixelSizeBehind": "4",
                "--fullWeight": "1",
                "--saveRawDensePointCloud": "false",
                "--voteFilteringForWeaklySupportedSurfaces": "true",
                "--invertTetrahedronBasedOnNeighborsNbIterations": "10",
                "--minSolidAngleRatio": "0.2",
                "--nbSolidAngleFilteringIterations": "2",
                "--maxNbConnectedHelperPoints": "50",
                "--exportDebugTetrahedralization": "false",
                "--seed": "20260721",
                "--verboseLevel": "info",
            }
            for flag, value in frozen_pairs.items():
                index = meshing.index(flag)
                self.assertEqual(meshing[index + 1], value, flag)
            self.assertIn("--maxInputPoints", meshing)
            self.assertIn("<RECONSTRUCTION_TOTAL_RASTER_PIXELS>", meshing)
            self.assertIn("--maxPoints", meshing)
            self.assertIn("<RECONSTRUCTION_VALID_DEPTH_POINTS_PLUS_ONE>", meshing)

            evaluation = commands["evaluation"]
            self.assertEqual(
                set(evaluation),
                {"prepare", "evaluate_tsdf", "evaluate_fusecut", "compare"},
            )
            self.assertIn("tools/python/b0_prepare_eval.py", evaluation["prepare"])
            for name in ("evaluate_tsdf", "evaluate_fusecut", "compare"):
                self.assertIn("tools/python/pw_mesh_bench.py", evaluation[name])
            self.assertIn("evaluate-mesh", evaluation["evaluate_tsdf"])
            self.assertIn("evaluate-mesh", evaluation["evaluate_fusecut"])
            self.assertIn("compare", evaluation["compare"])
            self.assertIn("--bootstrap-replicates", evaluation["compare"])
            bootstrap_index = evaluation["compare"].index("--bootstrap-replicates")
            self.assertEqual(evaluation["compare"][bootstrap_index + 1], "10000")
            seed_index = evaluation["compare"].index("--bootstrap-seed")
            self.assertEqual(evaluation["compare"][seed_index + 1], "20260721")

            dataset = contract["dataset_identity"]
            self.assertEqual(dataset["selected"], "trio_spatial_first100_fallback")
            self.assertFalse(dataset["selected_is_real_cap50_capture"])
            self.assertEqual(dataset["real_cap50_capture"]["status"], "NOT_SELECTED")

    def test_existing_output_is_rejected_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            out = root / "registration"
            out.mkdir()
            sentinel = out / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "output path already exists"):
                self._run_fixture(fixture, out)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(out.iterdir()), [sentinel])

    def test_spatial_manifest_mismatch_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            spatial = fixture["spatial_manifest"]
            payload = json.loads(spatial.read_text())
            payload["spatialOrder"][0], payload["spatialOrder"][1] = (
                payload["spatialOrder"][1],
                payload["spatialOrder"][0],
            )
            spatial.write_text(json.dumps(payload), encoding="utf-8")
            fixture["patches"]["EXPECTED_SPATIAL_MANIFEST_SHA256"] = prereg.sha256_file(
                spatial
            )
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "cap list does not match"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_trio_refs_order_mismatch_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            trio_refs = fixture["trio_refs"]
            payload = json.loads(trio_refs.read_text())
            payload["refs"][0], payload["refs"][1] = (
                payload["refs"][1],
                payload["refs"][0],
            )
            trio_refs.write_text(json.dumps(payload), encoding="utf-8")
            fixture["patches"]["EXPECTED_TRIO_REFS_SHA256"] = prereg.sha256_file(
                trio_refs
            )
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, prereg.ROUTE_INPUT_NOT_EQUIVALENT
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_relative_input_is_rejected_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "dmcache must be an absolute path"
            ):
                prereg.preregister(
                    dmcache=Path("relative-dmcache.npz"),
                    trio_model_lapa=fixture["model_cache"],
                    trio_refs=fixture["trio_refs"],
                    cap100_list=fixture["cap_list"],
                    spatial_manifest=fixture["spatial_manifest"],
                    code_root=fixture["code_root"],
                    alicevision_binary=fixture["alicevision_binary"],
                    out=out,
                )

            self.assertFalse(out.exists())

    def test_dmcache_signature_mismatch_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            np.savez(
                fixture["dmcache"],
                frames=np.asarray(fixture["all_frames"]),
                dm=np.ones((413, 2, 3), dtype=np.float32),
                sig=np.asarray("wrong-signature"),
            )
            fixture["patches"]["EXPECTED_DMCACHE_SHA256"] = prereg.sha256_file(
                fixture["dmcache"]
            )
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "dmcache signature mismatch"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_dmcache_shape_mismatch_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            np.savez(
                fixture["dmcache"],
                frames=np.asarray(fixture["all_frames"]),
                dm=np.ones((413, 2, 4), dtype=np.float32),
                sig=np.asarray("fixture-signature"),
            )
            fixture["patches"]["EXPECTED_DMCACHE_SHA256"] = prereg.sha256_file(
                fixture["dmcache"]
            )
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "dmcache depth contract mismatch"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_frozen_file_hash_mismatch_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            fixture["trio_refs"].write_bytes(fixture["trio_refs"].read_bytes() + b"\n")
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "trio_refs SHA-256 mismatch"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_incomplete_dirty_code_bundle_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            (fixture["code_root"] / "tools/python/b0_run_monitored.py").unlink()
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "dirty code bundle is incomplete"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())

    def test_nonexecutable_alicevision_binary_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._make_fixture(root)
            fixture["alicevision_binary"].chmod(0o644)
            out = root / "registration"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, "is not executable"
            ):
                self._run_fixture(fixture, out)

            self.assertFalse(out.exists())


class RealReadOnlyPreflightTests(unittest.TestCase):
    REAL_REPOSITORY = (
        Path.home() / "Developer/Aether3D-cross/pocketworld_research_benchmarks"
    )
    REAL_DMCACHE = REAL_REPOSITORY / "tools/python/diffmvs_out/dmcache_trio_ofull.npz"
    REAL_MODEL = REAL_REPOSITORY / "tools/python/diffmvs_out/trio_model_lapa.npz"
    REAL_REFS = REAL_REPOSITORY / "tools/python/diffmvs_out/trio_refs.json"
    REAL_SPATIAL = REAL_REPOSITORY / prereg.SPATIAL_MANIFEST_REPOSITORY_PATH
    REAL_CAP100 = REAL_REPOSITORY / "tools/python/sfm_cmp/bench50/image_list_100.txt"

    @unittest.skipUnless(
        all(
            path.is_file()
            for path in (REAL_DMCACHE, REAL_MODEL, REAL_REFS, REAL_SPATIAL, REAL_CAP100)
        ),
        "certified B0 inputs are not present on this host",
    )
    def test_real_frozen_inputs_pass_without_creating_outputs(self) -> None:
        inputs = (
            self.REAL_DMCACHE,
            self.REAL_MODEL,
            self.REAL_REFS,
            self.REAL_SPATIAL,
            self.REAL_CAP100,
        )
        before = [(path.stat().st_size, path.stat().st_mtime_ns) for path in inputs]

        result = prereg.preflight(
            dmcache=self.REAL_DMCACHE,
            trio_model_lapa=self.REAL_MODEL,
            trio_refs=self.REAL_REFS,
            spatial_manifest=self.REAL_SPATIAL,
            cap100_list=self.REAL_CAP100,
        )

        self.assertEqual(result["counts"]["cap100_reconstruction"], 81)
        self.assertEqual(result["counts"]["cap100_heldout"], 19)
        self.assertEqual(result["counts"]["full413_reconstruction"], 331)
        self.assertEqual(result["counts"]["full413_heldout"], 82)
        self.assertEqual(result["hashes"]["full413_heldout"], prereg.EXPECTED_FULL_HELDOUT_SHA256)
        self.assertEqual(result["hashes"]["full413_reconstruction"], prereg.EXPECTED_FULL_RECONSTRUCTION_SHA256)
        self.assertEqual(
            [(path.stat().st_size, path.stat().st_mtime_ns) for path in inputs], before
        )


class GenericRealCap50RegistrationTests(unittest.TestCase):
    SCALE = 1.007804831494465
    SPLIT_ID = "cap50_93r22h_strict"
    DATASET_ID = "cap50-real-115"
    REAL_ALICEVISION = Path(
        "/Users/kaidongwang/av_task_c/build/alicevision-generate/"
        "Darwin-arm64/aliceVision_meshing"
    )

    def test_formal_identity_constants_are_exact_cap50_115_contract(self) -> None:
        self.assertEqual(prereg.FORMAL_DATASET_ID, "cap50-real-115")
        self.assertEqual(prereg.FORMAL_SPLIT_ID, "cap50_93r22h_strict")
        self.assertEqual(
            prereg.FORMAL_UNIVERSE_FRAME_ORDER_SHA256,
            "b632e81a048b1de96d36539e2edab67b0a721f7447d0392369cf2f96cf500c61",
        )
        self.assertEqual(
            prereg.FORMAL_RECONSTRUCTION_LIST_SHA256,
            "8ef00f3b310ed5d3c0ee00ff49f92e46cdfbadf703faec23e46a203367822666",
        )
        self.assertEqual(
            prereg.FORMAL_HELDOUT_LIST_SHA256,
            "2cf47fa3fcdb329711f762bfd360668158d3fb5915d7fd754bdfc2d6df577980",
        )

    def _fixture(self, root: Path) -> dict[str, object]:
        names = [f"device_A_{index:03d}_tap-{1000 + index}.jpg" for index in range(115)]
        reconstruction = names[:93]
        heldout = names[93:]
        image_root = root / "images"
        image_root.mkdir()
        image_identities: dict[str, dict[str, object]] = {}
        for index, name in enumerate(names):
            image = image_root / name
            image.write_bytes(f"jpeg-fixture-{index}\n".encode("ascii"))
            image_identities[name] = {
                "sha256": prereg.sha256_file(image),
                "size_bytes": image.stat().st_size,
            }

        common_root = (root / "common-cache").resolve()
        common_root.mkdir()
        dmcache = common_root / "dmcache.npz"
        depth = np.ones((115, 2, 3), dtype=np.float32)
        depth[:, 0, 0] = 0.0
        np.savez_compressed(
            dmcache,
            frames=np.asarray(names),
            dm=depth,
            sig=np.asarray("cap50-common-camera-z-v1"),
            metres_per_model_unit=np.asarray(self.SCALE, dtype=np.float64),
        )

        model_cache = common_root / "model_cache.npz"
        model_names = names[17:] + names[:17]
        K = np.repeat(np.eye(3, dtype=np.float32)[None], 115, axis=0)
        K[:, 0, 0] = 500.0
        K[:, 1, 1] = 500.0
        w2c = np.repeat(np.eye(4, dtype=np.float32)[None], 115, axis=0)
        np.savez_compressed(
            model_cache,
            names=np.asarray(model_names),
            K=K,
            w2c=w2c,
            metres_per_model_unit=np.asarray(self.SCALE, dtype=np.float64),
        )

        payload: dict[str, object] = {
            "schema_version": "b0-input-contract-v1",
            "dataset_id": self.DATASET_ID,
            "coordinate_frame": "optimized_sfm_cv",
            "metres_per_model_unit": self.SCALE,
            "transductive_policy": {
                "present": True,
                "route_allowed": True,
                "quality_scoring_forbidden": False,
                "reason": "fixture optimized SfM contains all camera poses",
            },
            "dmcache": {
                "path": str(dmcache.resolve()),
                "sha256": prereg.sha256_file(dmcache),
                "signature": "cap50-common-camera-z-v1",
                "depth": {"shape": [115, 2, 3], "dtype": "float32"},
                "frame_order": names,
                "frame_order_sha256": shared_contract.ordered_frame_names_sha256(names),
            },
            "model_cache": {
                "path": str(model_cache.resolve()),
                "sha256": prereg.sha256_file(model_cache),
                "frame_order": model_names,
                "frame_order_sha256": shared_contract.ordered_frame_names_sha256(
                    model_names
                ),
            },
            "splits": {
                self.SPLIT_ID: {
                    "dataset_id": self.DATASET_ID,
                    "route_allowed": True,
                    "quality_scoring_forbidden": False,
                    "reconstruction": {
                        "frames": reconstruction,
                        "file_sha256": shared_contract.ordered_frame_names_sha256(
                            reconstruction
                        ),
                        "semantic_sha256": shared_contract.ordered_frame_names_sha256(
                            reconstruction
                        ),
                    },
                    "heldout": {
                        "frames": heldout,
                        "file_sha256": shared_contract.ordered_frame_names_sha256(
                            heldout
                        ),
                        "semantic_sha256": shared_contract.ordered_frame_names_sha256(
                            heldout
                        ),
                    },
                }
            },
            "images": {
                "root": str(image_root.resolve()),
                "raw_size_wh": [3840, 2160],
                "root_manifest_sha256": shared_contract.image_identity_manifest_sha256(
                    names, image_identities
                ),
                "by_name": image_identities,
            },
        }
        input_contract = common_root / "input_contract.json"
        input_contract.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        code_root = root / "code"
        for relative_path in prereg.FROZEN_CODE_RELATIVE_PATHS:
            script = code_root / relative_path
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(f"# {relative_path}\n", encoding="utf-8")
        alicevision_binary = root / "aliceVision_meshing"
        alicevision_binary.write_bytes(b"fixture executable\n")
        alicevision_binary.chmod(0o755)

        producer_inputs = root / "producer-inputs"
        producer_inputs.mkdir()
        producer_files: dict[str, Path] = {}
        for option in (
            "metadata",
            "sfm-meta",
            "sfm-frames",
            "arbitration-plan",
            "sparse-points",
        ):
            source = producer_inputs / f"{option}.fixture"
            source.write_text(f"{option}\n", encoding="utf-8")
            producer_files[option] = source.resolve()
        producer_model = producer_inputs / "CasDiffMVS_fp32.mlpackage"
        producer_model.mkdir()
        (producer_model / "Manifest.json").write_text("{}\n", encoding="utf-8")
        producer_script = (
            code_root / prereg.FORMAL_INPUT_PRODUCER_RELATIVE_PATH
        ).resolve()
        producer_command = [
            str(Path(sys.executable).resolve()),
            str(producer_script),
            "--metadata",
            str(producer_files["metadata"]),
            "--sfm-meta",
            str(producer_files["sfm-meta"]),
            "--sfm-frames",
            str(producer_files["sfm-frames"]),
            "--arbitration-plan",
            str(producer_files["arbitration-plan"]),
            "--sparse-points",
            str(producer_files["sparse-points"]),
            "--image-root",
            str(image_root.resolve()),
            "--model",
            str(producer_model.resolve()),
            "--out",
            str(common_root),
            "--dataset-id",
            self.DATASET_ID,
            "--metres-per-model-unit",
            str(self.SCALE),
            "--compute-units",
            "cpu_and_gpu",
        ]
        provenance = common_root / "provenance.json"
        provenance.write_text(
            json.dumps(
                {
                    "schema_version": "b0-cap50-common-cache-provenance-v1",
                    "status": "complete",
                    "dry_contract": False,
                    "publishable_as_full": True,
                    "run_mode": "full_common_cache",
                    "requested_limit": None,
                    "generator": {
                        "script": str(producer_script),
                        "script_sha256": prereg.sha256_file(producer_script),
                    },
                    "final_input_contract": {
                        "path": str(input_contract.resolve()),
                        "sha256": prereg.sha256_file(input_contract),
                        "schema_version": "b0-input-contract-v1",
                        "prewrite_validated": True,
                        "postwrite_reloaded_and_hash_verified": True,
                    },
                    "dmcache": {
                        "path": str(dmcache.resolve()),
                        "sha256": prereg.sha256_file(dmcache),
                    },
                    "model_cache": {
                        "path": str(model_cache.resolve()),
                        "sha256": prereg.sha256_file(model_cache),
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        attested_paths = (
            input_contract.resolve(),
            dmcache.resolve(),
            model_cache.resolve(),
            provenance.resolve(),
        )
        attested_files = [
            {
                "schema_version": "b0-attested-file-v1",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": prereg.sha256_file(path),
            }
            for path in attested_paths
        ]
        attestation_payload = {
            "files": attested_files,
            "trees": [prereg._current_tree_attestation(common_root)],
        }
        producer_status_root = root / "producer-monitor"
        producer_status_root.mkdir()
        producer_status = producer_status_root / "status.json"
        producer_status.write_text(
            json.dumps(
                {
                    "schema_version": "b0-monitored-command-v1",
                    "verdict": "PASS",
                    "command_outcome": "SUCCESS",
                    "started": True,
                    "exit_code": 0,
                    "launch_error": None,
                    "command": {
                        "argv": producer_command,
                        "canonical_sha256": prereg._canonical_json_sha256(
                            producer_command
                        ),
                        "shell": False,
                    },
                    "attestation": {
                        "status": "VERIFIED",
                        **attestation_payload,
                        "bundle_sha256": prereg._canonical_json_sha256(
                            attestation_payload
                        ),
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "names": names,
            "reconstruction": reconstruction,
            "heldout": heldout,
            "payload": payload,
            "input_contract": input_contract,
            "dmcache": dmcache,
            "model_cache": model_cache,
            "image_root": image_root,
            "code_root": code_root,
            "alicevision_binary": alicevision_binary,
            "producer_status": producer_status.resolve(),
            "producer_command": producer_command,
            "provenance": provenance.resolve(),
            "common_root": common_root,
            "formal_hash_patches": {
                "FORMAL_UNIVERSE_FRAME_ORDER_SHA256": (
                    payload["dmcache"]["frame_order_sha256"]
                ),
                "FORMAL_RECONSTRUCTION_LIST_SHA256": (
                    payload["splits"][self.SPLIT_ID]["reconstruction"][
                        "semantic_sha256"
                    ]
                ),
                "FORMAL_HELDOUT_LIST_SHA256": (
                    payload["splits"][self.SPLIT_ID]["heldout"][
                        "semantic_sha256"
                    ]
                ),
            },
        }

    def _run(
        self,
        fixture: dict[str, object],
        out: Path,
        *,
        run_root: Path | None = None,
    ) -> dict[str, object]:
        if run_root is None:
            run_root = out.parent / f"{out.name}-run"
        with mock.patch.multiple(prereg, **fixture["formal_hash_patches"]):
            return prereg.preregister_from_input_contract(
                input_contract_path=fixture["input_contract"],
                split_id=self.SPLIT_ID,
                code_root=fixture["code_root"],
                alicevision_binary=fixture["alicevision_binary"],
                input_producer_monitor_status=fixture["producer_status"],
                run_root=run_root,
                out=out,
            )

    def test_freezes_exact_contract_owned_real_cap50_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            out = root / "preregistered"
            run_root = (root / "formal-run").resolve()

            result = self._run(fixture, out, run_root=run_root)

            self.assertEqual(result["dataset_id"], self.DATASET_ID)
            self.assertEqual(result["split_id"], self.SPLIT_ID)
            self.assertEqual(result["universe_count"], 115)
            self.assertEqual(result["reconstruction_count"], 93)
            self.assertEqual(result["heldout_count"], 22)
            self.assertEqual(result["run_root"], str(run_root.resolve()))
            self.assertFalse(run_root.exists())
            self.assertEqual(
                (out / "input_contract.raw.json").read_bytes(),
                fixture["input_contract"].read_bytes(),
            )

            contract = json.loads((out / "contract.json").read_text())
            identity = contract["frozen_authority"]["input_contract"]
            self.assertEqual(identity["raw_sha256"], prereg.sha256_file(fixture["input_contract"]))
            self.assertEqual(identity["dataset_id"], self.DATASET_ID)
            self.assertEqual(identity["split_id"], self.SPLIT_ID)
            self.assertEqual(identity["coordinate_frame"], "optimized_sfm_cv")
            self.assertEqual(identity["metres_per_model_unit"], self.SCALE)
            self.assertEqual(identity["universe_count"], 115)
            self.assertEqual(identity["reconstruction_count"], 93)
            self.assertEqual(identity["heldout_count"], 22)
            self.assertEqual(
                identity["universe_frame_order_sha256"],
                fixture["payload"]["dmcache"]["frame_order_sha256"],
            )
            data = contract["frozen_authority"]["data_sha256"]
            self.assertEqual(data["dmcache"], prereg.sha256_file(fixture["dmcache"]))
            self.assertEqual(data["model_cache"], prereg.sha256_file(fixture["model_cache"]))
            self.assertEqual(
                data["images_root_manifest"],
                fixture["payload"]["images"]["root_manifest_sha256"],
            )
            producer = contract["frozen_authority"]["input_producer_monitor"]
            self.assertEqual(producer["verdict"], "PASS")
            self.assertEqual(
                producer["status_sha256"],
                prereg.sha256_file(fixture["producer_status"]),
            )
            self.assertEqual(producer["child_argv"], fixture["producer_command"])
            self.assertEqual(
                producer["provenance_sha256"],
                prereg.sha256_file(fixture["provenance"]),
            )
            self.assertEqual(
                producer["output_tree"]["path"], str(fixture["common_root"])
            )
            self.assertEqual(
                producer["output_tree"],
                prereg._current_tree_attestation(fixture["common_root"]),
            )
            modules = contract["frozen_authority"]["environment_identity"][
                "identity"
            ]["required_python_modules"]
            self.assertEqual(
                {name: modules[name]["version"] for name in prereg.REQUIRED_PYTHON_MODULES},
                {
                    "OpenEXR": "3.4.12",
                    "cv2": "4.13.0",
                    "open3d": "0.19.0",
                    "numpy": "2.4.2",
                },
            )
            self.assertTrue(modules["OpenEXR"]["capability_present"])

            recon_path = out / "lists" / f"{self.SPLIT_ID}_reconstruction.txt"
            heldout_path = out / "lists" / f"{self.SPLIT_ID}_heldout.txt"
            self.assertEqual(recon_path.read_bytes(), _list_bytes(fixture["reconstruction"]))
            self.assertEqual(heldout_path.read_bytes(), _list_bytes(fixture["heldout"]))

            rows = contract["controlled_variable_table"]
            differing = [row for row in rows if row["tsdf"] != row["fusecut"]]
            self.assertEqual([row["factor"] for row in differing], ["meshing_backend"])
            self.assertTrue(differing[0]["only_experimental_difference"])
            self.assertEqual(
                contract["gates"]["b0_prompt_strict"],
                {
                    "coverage_delta_min": -0.02,
                    "unsupported_gt_20mm_delta_max": 0.02,
                    "median_absrel_delta_max": 0.005,
                    "p95_absrel_delta_max": 0.02,
                    "median_normal_error_delta_max_deg": 2.0,
                    "double_shell_rate_delta_max": 0.01,
                    "double_shell_p95_separation_delta_max_m": 0.005,
                    "nonmanifold_edge_fraction_max": 1e-4,
                    "finite_vertices_and_faces_required": True,
                },
            )

            commands = contract["execution_plan"]["commands"]
            raw_contract = str((out / "input_contract.raw.json").resolve())
            shared_binding = contract["execution_plan"]["shared_input_binding"]
            self.assertEqual(shared_binding["input_contract"], raw_contract)
            self.assertEqual(shared_binding["split_id"], self.SPLIT_ID)
            self.assertEqual(shared_binding["dataset_id"], self.DATASET_ID)

            def child(command: list[str]) -> list[str]:
                return command[command.index("--") + 1 :]

            for command_name in ("tsdf_meshing", "fusecut_export"):
                command = commands[command_name]
                child_command = child(command)
                self.assertIn(raw_contract, child_command)
                self.assertIn("--split-id", child_command)
                split_index = child_command.index("--split-id")
                self.assertEqual(child_command[split_index + 1], self.SPLIT_ID)
                poll_index = commands[command_name].index("--resource-poll-seconds")
                self.assertEqual(commands[command_name][poll_index + 1], "1")
            meshing_wrapper = commands["fusecut_meshing"]
            meshing = child(meshing_wrapper)
            self.assertIn("--output", meshing)
            self.assertIn("--outputMesh", meshing)
            self.assertEqual(meshing[meshing.index("--seed") + 1], "20260721")
            self.assertEqual(
                meshing_wrapper[
                    meshing_wrapper.index("--resource-poll-seconds") + 1
                ],
                "1",
            )
            self.assertEqual(
                meshing[meshing.index("--maxInputPoints") + 1], "558"
            )
            self.assertEqual(meshing[meshing.index("--maxPoints") + 1], "466")

            evaluation = commands["evaluation"]
            prepare = child(evaluation["prepare"])
            self.assertIn(raw_contract, prepare)
            self.assertEqual(prepare[prepare.index("--split-id") + 1], self.SPLIT_ID)
            for command_name in ("evaluate_tsdf", "evaluate_fusecut", "compare"):
                command = child(evaluation[command_name])
                self.assertIn(str((out / "contract.json").resolve()), command)
                self.assertNotIn("--dataset-id", command)
                self.assertEqual(
                    command[command.index("--input-contract") + 1], raw_contract
                )
                self.assertEqual(
                    command[command.index("--split-id") + 1], self.SPLIT_ID
                )
                import pw_mesh_bench

                parsed = pw_mesh_bench._parser().parse_args(command[2:])
                self.assertEqual(parsed.input_contract, Path(raw_contract))
                self.assertEqual(parsed.split_id, self.SPLIT_ID)
            compare = evaluation["compare"]
            compare = child(compare)
            self.assertEqual(compare[compare.index("--bootstrap-replicates") + 1], "10000")
            self.assertEqual(compare[compare.index("--bootstrap-seed") + 1], "20260721")

            plan = contract["execution_plan"]
            self.assertEqual(
                plan["run_root_rule"],
                {
                    "path": str(run_root.resolve()),
                    "must_be_absolute": True,
                    "must_not_exist_at_preregistration": True,
                    "observed_absent_at_preregistration": True,
                    "created_by_preregistration": False,
                },
            )
            budgets = plan["alicevision_point_budgets"]
            self.assertEqual(budgets["depth_shape"], [115, 2, 3])
            self.assertEqual(budgets["reconstruction_frame_count"], 93)
            self.assertEqual(budgets["reconstruction_valid_depth_points"], 465)
            self.assertEqual(budgets["maxInputPoints"], 558)
            self.assertEqual(budgets["maxPoints"], 466)

            phase_commands = {
                "tsdf_meshing": commands["tsdf_meshing"],
                "fusecut_export": commands["fusecut_export"],
                "fusecut_meshing": commands["fusecut_meshing"],
                "evaluation_prepare": evaluation["prepare"],
                "evaluate_tsdf": evaluation["evaluate_tsdf"],
                "evaluate_fusecut": evaluation["evaluate_fusecut"],
                "evaluation_compare": evaluation["compare"],
            }
            bindings = plan["formal_runner_bindings"]
            self.assertEqual(set(bindings), set(phase_commands))
            python_executable = str(Path(sys.executable).resolve())
            import b0_run_monitored

            for phase, wrapper in phase_commands.items():
                self.assertEqual(wrapper[0], python_executable)
                self.assertEqual(
                    wrapper[wrapper.index("--preregistered-contract") + 1],
                    str((out / "contract.json").resolve()),
                )
                self.assertEqual(wrapper[wrapper.index("--phase") + 1], phase)
                child_argv = child(wrapper)
                self.assertEqual(bindings[phase]["child_argv"], child_argv)
                self.assertEqual(
                    bindings[phase]["child_argv_sha256"],
                    prereg._canonical_json_sha256(child_argv),
                )
                if phase != "fusecut_meshing":
                    self.assertEqual(child_argv[0], python_executable)
                parsed_wrapper = b0_run_monitored.build_parser().parse_args(
                    wrapper[2:]
                )
                parsed_child, _ = b0_run_monitored.validate_cli_args(
                    parsed_wrapper
                )
                self.assertEqual(parsed_child, child_argv)

            monitor_root = run_root / "monitor"
            expected_attest_files = {
                "tsdf_meshing": {
                    run_root / "tsdf" / "mesh.ply",
                    run_root / "tsdf" / "provenance.json",
                },
                "fusecut_export": {
                    run_root / "fusecut" / "export" / "provenance.json"
                },
                "fusecut_meshing": {
                    run_root / "fusecut" / "mesh.obj",
                    run_root / "fusecut" / "dense.sfm",
                },
                "evaluation_prepare": {
                    run_root / "evaluation" / "prepared_input_masks.npz",
                    run_root
                    / "evaluation"
                    / "prepared_input_masks.npz.provenance.json",
                },
                "evaluate_tsdf": {run_root / "evaluation" / "tsdf.json"},
                "evaluate_fusecut": {
                    run_root / "evaluation" / "fusecut.json"
                },
                "evaluation_compare": {
                    run_root / "evaluation" / "comparison.json"
                },
            }
            expected_attest_trees = {
                "fusecut_export": {run_root / "fusecut" / "export"}
            }
            expected_prior_statuses = {
                "fusecut_meshing": {
                    monitor_root / "fusecut_export" / "status.json"
                },
                "evaluate_tsdf": {
                    monitor_root / "tsdf_meshing" / "status.json",
                    monitor_root / "evaluation_prepare" / "status.json",
                },
                "evaluate_fusecut": {
                    monitor_root / "fusecut_meshing" / "status.json",
                    monitor_root / "evaluation_prepare" / "status.json",
                },
                "evaluation_compare": {
                    monitor_root / "evaluate_tsdf" / "status.json",
                    monitor_root / "evaluate_fusecut" / "status.json",
                },
            }
            for phase, wrapper in phase_commands.items():
                parsed_wrapper = b0_run_monitored.build_parser().parse_args(
                    wrapper[2:]
                )
                self.assertEqual(
                    set(parsed_wrapper.attest_file),
                    expected_attest_files[phase],
                )
                self.assertEqual(
                    set(parsed_wrapper.attest_tree),
                    expected_attest_trees.get(phase, set()),
                )
                self.assertEqual(
                    set(parsed_wrapper.require_prior_status),
                    expected_prior_statuses.get(phase, set()),
                )
            self.assertNotIn("<", json.dumps(commands, sort_keys=True))
            self.assertNotIn(">", json.dumps(commands, sort_keys=True))

    def test_physical_identity_mutation_fails_without_creating_output(self) -> None:
        mutations = {
            "dmcache": lambda fixture: fixture["dmcache"].write_bytes(
                fixture["dmcache"].read_bytes() + b"mutation"
            ),
            "model_cache": lambda fixture: fixture["model_cache"].write_bytes(
                fixture["model_cache"].read_bytes() + b"mutation"
            ),
            "image": lambda fixture: (
                fixture["image_root"] / fixture["names"][37]
            ).write_bytes(b"mutated image"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = self._fixture(root)
                mutate(fixture)
                out = root / "preregistered"
                with self.assertRaisesRegex(
                    prereg.PreRegistrationError,
                    prereg.ROUTE_INPUT_NOT_EQUIVALENT,
                ):
                    self._run(fixture, out)
                self.assertFalse(out.exists())

    def test_contract_owned_split_is_not_recomputed_or_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            payload = fixture["payload"]
            reconstruction = payload["splits"][self.SPLIT_ID]["reconstruction"]
            reconstruction["frames"][0] = "forged_tap-name.jpg"
            fixture["input_contract"].write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            out = root / "preregistered"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, prereg.ROUTE_INPUT_NOT_EQUIVALENT
            ):
                self._run(fixture, out)

            self.assertFalse(out.exists())

    def test_self_consistent_alternate_115_frame_cohort_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            out = root / "preregistered"
            run_root = root / "formal-run"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, prereg.ROUTE_INPUT_NOT_EQUIVALENT
            ):
                prereg.preregister_from_input_contract(
                    input_contract_path=fixture["input_contract"],
                    split_id=self.SPLIT_ID,
                    code_root=fixture["code_root"],
                    alicevision_binary=fixture["alicevision_binary"],
                    input_producer_monitor_status=fixture["producer_status"],
                    run_root=run_root,
                    out=out,
                )

            self.assertFalse(out.exists())
            self.assertFalse(run_root.exists())

    def test_unverified_or_nonfull_input_producer_is_rejected_without_writes(self) -> None:
        def failed_verdict(fixture: dict[str, object], status: dict[str, object]) -> None:
            status["verdict"] = "COMMAND_FAILED"

        def limited_command(fixture: dict[str, object], status: dict[str, object]) -> None:
            status["command"]["argv"].extend(["--limit", "1"])
            status["command"]["canonical_sha256"] = prereg._canonical_json_sha256(
                status["command"]["argv"]
            )

        def dry_command(fixture: dict[str, object], status: dict[str, object]) -> None:
            status["command"]["argv"].append("--dry-contract")
            status["command"]["canonical_sha256"] = prereg._canonical_json_sha256(
                status["command"]["argv"]
            )

        def missing_attestation(
            fixture: dict[str, object], status: dict[str, object]
        ) -> None:
            status["attestation"]["files"].pop()
            payload = {
                "files": status["attestation"]["files"],
                "trees": status["attestation"]["trees"],
            }
            status["attestation"]["bundle_sha256"] = prereg._canonical_json_sha256(
                payload
            )

        def changed_provenance(
            fixture: dict[str, object], status: dict[str, object]
        ) -> None:
            fixture["provenance"].write_text("{}\n", encoding="utf-8")

        def extra_tree(fixture: dict[str, object], status: dict[str, object]) -> None:
            status["attestation"]["trees"].append(
                dict(status["attestation"]["trees"][0])
            )
            payload = {
                "files": status["attestation"]["files"],
                "trees": status["attestation"]["trees"],
            }
            status["attestation"]["bundle_sha256"] = prereg._canonical_json_sha256(
                payload
            )

        def wrong_tree(fixture: dict[str, object], status: dict[str, object]) -> None:
            status["attestation"]["trees"][0]["path"] = str(
                Path(fixture["common_root"]).parent
            )
            payload = {
                "files": status["attestation"]["files"],
                "trees": status["attestation"]["trees"],
            }
            status["attestation"]["bundle_sha256"] = prereg._canonical_json_sha256(
                payload
            )

        def stale_tree(fixture: dict[str, object], status: dict[str, object]) -> None:
            (Path(fixture["common_root"]) / "late-artifact.bin").write_bytes(b"late")

        mutations = {
            "failed-verdict": failed_verdict,
            "limit": limited_command,
            "dry-contract": dry_command,
            "missing-attestation": missing_attestation,
            "changed-provenance": changed_provenance,
            "extra-tree": extra_tree,
            "wrong-tree": wrong_tree,
            "stale-tree": stale_tree,
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fixture = self._fixture(root)
                status_path = fixture["producer_status"]
                status = json.loads(status_path.read_text(encoding="utf-8"))
                mutate(fixture, status)
                status_path.write_text(
                    json.dumps(status, indent=2) + "\n", encoding="utf-8"
                )
                out = root / "preregistered"

                with self.assertRaisesRegex(
                    prereg.PreRegistrationError,
                    prereg.ROUTE_INPUT_NOT_EQUIVALENT,
                ):
                    self._run(fixture, out, run_root=root / "formal-run")

                self.assertFalse(out.exists())
                self.assertFalse((root / "formal-run").exists())

    def test_run_root_must_be_absolute_new_and_disjoint_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            invalid_roots = {
                "relative": Path("relative-run-root"),
                "existing": root / "existing-run-root",
                "contains_output": root / "run-parent",
            }
            invalid_roots["existing"].mkdir()
            for label, run_root in invalid_roots.items():
                with self.subTest(label=label):
                    out = (
                        run_root / "preregistered"
                        if label == "contains_output"
                        else root / f"preregistered-{label}"
                    )
                    with self.assertRaises(
                        (prereg.PreRegistrationError, FileExistsError)
                    ):
                        self._run(fixture, out, run_root=run_root)
                    self.assertFalse(out.exists())

    @unittest.skipUnless(
        REAL_ALICEVISION.is_file() and os.access(REAL_ALICEVISION, os.X_OK),
        "native AliceVision meshing binary is not present on this host",
    )
    def test_generated_alicevision_budget_arguments_parse_as_integers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            fixture["alicevision_binary"] = self.REAL_ALICEVISION
            out = root / "preregistered"
            run_root = root / "formal-run"
            self._run(fixture, out, run_root=run_root)
            contract = json.loads((out / "contract.json").read_text())
            wrapper = contract["execution_plan"]["commands"]["fusecut_meshing"]
            child = wrapper[wrapper.index("--") + 1 :]
            # Exercise the exact verified real-cap50 decimal budgets, not only
            # the tiny unit-fixture values.
            child[child.index("--maxInputPoints") + 1] = "42663936"
            child[child.index("--maxPoints") + 1] = "7468701"

            completed = subprocess.run(
                child,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30.0,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("invalid integer", completed.stderr.lower())
            self.assertNotIn("invalid integer", completed.stdout.lower())
            self.assertFalse(run_root.exists())

    def test_formal_gate_rejects_mutated_contract_owned_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            payload = fixture["payload"]
            payload["metres_per_model_unit"] = 1.0
            fixture["input_contract"].write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            out = root / "preregistered"

            with self.assertRaisesRegex(
                prereg.PreRegistrationError, prereg.ROUTE_INPUT_NOT_EQUIVALENT
            ):
                self._run(fixture, out)

            self.assertFalse(out.exists())

    def test_formal_cli_requires_only_generic_contract_identity_arguments(self) -> None:
        base = [
            "--input-contract", "/abs/input.json",
            "--split-id", self.SPLIT_ID,
            "--code-root", "/abs/code",
            "--alicevision-binary", "/abs/aliceVision_meshing",
            "--input-producer-monitor-status", "/abs/producer-status.json",
            "--run-root", "/abs/brand-new-run",
            "--out", "/abs/new-output",
        ]
        parsed = prereg._build_parser().parse_args(base)
        self.assertEqual(parsed.split_id, self.SPLIT_ID)
        for flag in (
            "--input-contract",
            "--split-id",
            "--code-root",
            "--alicevision-binary",
            "--input-producer-monitor-status",
            "--run-root",
            "--out",
        ):
            argv = list(base)
            index = argv.index(flag)
            del argv[index:index + 2]
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                prereg._build_parser().parse_args(argv)


if __name__ == "__main__":
    unittest.main()
