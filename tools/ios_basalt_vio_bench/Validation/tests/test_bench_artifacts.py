import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_bench_artifact import (
    validate_artifact_manifest,
    validate_heartbeat,
    validate_metric_definitions,
    validate_receipt,
    validate_transition,
)


ROOT = Path(__file__).resolve().parents[2]
METRIC_DEFINITIONS = ROOT / "Schemas" / "metric_definitions.v1.json"
SHA = "a" * 64


def receipt(state="started", channel="live_soak"):
    document = {
        "schema_version": 1,
        "run_id": "d94f40fc-2c5d-4fa6-a936-8f789d752f64",
        "experiment_id": "vio-iphone-three-arm-v1-20260829",
        "state": state,
        "channel": channel,
        "input_camera_count": 1,
        "started_at_utc": "2026-08-29T10:00:00.000Z",
        "scope": "same_device_same_os_shared_capture_contract_and_identical_replay_manifest",
        "global_default_eligible": False,
        "app": {
            "bundle_id": "com.kyle.viobench",
            "uses_arkit": False,
            "backend": "cpu",
            "algorithm_mode": "basalt_vio_only_float",
            "engine_id": "basalt",
            "upstream_revision": "0f3b2b52c807f70ff4e2973ce253c73329eea7bc",
            "opencv_version": "4.12.0",
        },
        "device": {
            "model_identifier": "iPhone15,2",
            "operating_system_version": "Version 26.0 (Build 23A000)",
        },
        "identities": {
            "contract_sha256": SHA,
            "app_binary_sha256": "b" * 64,
            "engine_artifact_sha256": "f" * 64,
            "config_sha256": "c" * 64,
            "input_definition_sha256": "d" * 64,
            "metric_definitions_sha256": "e" * 64,
        },
        "power": {
            "power_w": None,
            "power_w_status": "unavailable_public_api",
            "battery_and_thermal_are_proxies": True,
        },
        "accuracy": {
            "status": "not_evaluable" if channel == "live_soak" else "evaluable",
            "ground_truth": "none" if channel == "live_soak" else "euroc",
        },
        "metrics": {},
    }
    if state != "started":
        document["ended_at_utc"] = "2026-08-29T10:15:00.000Z"
        document["termination"] = {
            "reason_code": "thresholds_met",
            "recovered_from_interruption": False,
        }
    return document


def terminal(state, channel="live_soak"):
    document = receipt(state, channel)
    if state in {"valid_pass", "valid_fail"}:
        if channel == "live_soak":
            document["metrics"] = {
                "processed_fps": 29.5,
                "p95_pipeline_latency_ms": 48.0,
                "app_drop_rate": 0.002,
                "thermal_critical_seconds": 0.0,
                "thermal_serious_seconds": 0.0,
                "peak_phys_footprint_mb": 410.0,
                "finite_pose_ratio": 1.0,
                "battery_level_delta": -0.08,
                "cpu_seconds": 620.0,
            }
        else:
            document["metrics"] = {
                "processed_fps": 31.0,
                "ate_rmse_m": 0.04,
                "rpe_translation_rmse_m": 0.02,
                "rpe_rotation_rmse_deg": 1.4,
                "ground_truth_coverage": 0.998,
                "cpu_seconds": 80.0,
            }
    if state == "valid_fail":
        document["termination"]["reason_code"] = "gates_not_met"
    elif state == "invalid":
        document["termination"]["reason_code"] = "capture_interruption"
    elif state == "aborted":
        document["termination"] = {
            "reason_code": "interrupted_recovery",
            "recovered_from_interruption": True,
        }
    return document


class ReceiptValidationTests(unittest.TestCase):
    def test_all_declared_states_validate(self):
        self.assertEqual([], validate_receipt(receipt()))
        for state in ("valid_pass", "valid_fail", "invalid", "aborted"):
            self.assertEqual([], validate_receipt(terminal(state)), state)

    def test_replay_channels_require_evaluable_accuracy_and_metrics(self):
        for channel in ("replay_paced", "replay_max"):
            self.assertEqual([], validate_receipt(terminal("valid_pass", channel)))

    def test_input_camera_count_is_required_and_live_is_mono(self):
        document = receipt()
        del document["input_camera_count"]
        self.assertIn("input_camera_count is required", validate_receipt(document))
        document = receipt()
        document["input_camera_count"] = 2
        self.assertIn("live_soak input_camera_count must be 1", validate_receipt(document))

    def test_replay_explicitly_distinguishes_mono_from_stereo(self):
        mono = terminal("valid_pass", "replay_paced")
        stereo = copy.deepcopy(mono)
        stereo["input_camera_count"] = 2
        self.assertEqual([], validate_receipt(mono))
        self.assertEqual([], validate_receipt(stereo))

    def test_rejects_missing_sha256_identity(self):
        document = receipt()
        del document["identities"]["app_binary_sha256"]
        self.assertIn("identities.app_binary_sha256 is required", validate_receipt(document))

    def test_rejects_non_sha256_identity(self):
        document = receipt()
        document["identities"]["config_sha256"] = "deadbeef"
        self.assertIn("identities.config_sha256 must be 64 lowercase hex characters", validate_receipt(document))

    def test_rejects_arkit_mislabeled_on_a_non_arkit_arm_and_production_bundle(self):
        document = receipt()
        document["app"]["uses_arkit"] = True
        self.assertIn("app.uses_arkit does not match engine_id", validate_receipt(document))
        document = receipt()
        document["app"]["bundle_id"] = "com.kyle.PocketWorld"
        self.assertIn("production bundle is forbidden", validate_receipt(document))

    def test_accepts_explicit_arkit_reference_identity_for_live_only(self):
        document = receipt()
        document["app"].update({
            "uses_arkit": True,
            "backend": "apple_arkit",
            "algorithm_mode": "arkit_world_tracking_reference",
            "engine_id": "arkit_reference",
            "upstream_revision": "apple_arkit_ios26_sdk",
            "opencv_version": "not_applicable",
        })
        self.assertEqual(validate_receipt(document), [])

    def test_rejects_fabricated_power(self):
        document = receipt()
        document["power"]["power_w"] = 2.7
        self.assertIn("power.power_w must be null", validate_receipt(document))

    def test_rejects_global_default_claim(self):
        document = receipt()
        document["global_default_eligible"] = True
        self.assertIn("global_default_eligible must be false", validate_receipt(document))

    def test_live_accuracy_is_not_evaluable(self):
        document = receipt()
        document["accuracy"] = {"status": "evaluable", "ground_truth": "arkit"}
        errors = validate_receipt(document)
        self.assertIn("live_soak accuracy.status must be not_evaluable", errors)
        self.assertIn("ARKit ground truth is forbidden", errors)

    def test_terminal_times_and_metrics_are_required(self):
        document = terminal("valid_pass")
        del document["ended_at_utc"]
        del document["metrics"]["processed_fps"]
        errors = validate_receipt(document)
        self.assertIn("ended_at_utc is required for terminal states", errors)
        self.assertIn("metrics.processed_fps is required for a valid live_soak result", errors)


class TransitionTests(unittest.TestCase):
    def test_started_can_transition_to_each_terminal_state(self):
        previous = receipt()
        for state in ("valid_pass", "valid_fail", "invalid", "aborted"):
            self.assertEqual([], validate_transition(previous, terminal(state)), state)

    def test_rejects_terminal_rewrite_and_started_rewrite(self):
        self.assertIn(
            "illegal receipt transition valid_pass -> valid_fail",
            validate_transition(terminal("valid_pass"), terminal("valid_fail")),
        )
        self.assertIn(
            "illegal receipt transition started -> started",
            validate_transition(receipt(), receipt()),
        )

    def test_interrupted_recovery_is_explicit_and_identity_preserving(self):
        previous = receipt()
        recovered = terminal("aborted")
        self.assertEqual([], validate_transition(previous, recovered))
        tampered = copy.deepcopy(recovered)
        tampered["identities"]["config_sha256"] = "f" * 64
        self.assertIn("identities must not change across a run", validate_transition(previous, tampered))
        tampered = copy.deepcopy(recovered)
        tampered["input_camera_count"] = 2
        self.assertIn("input_camera_count must not change across a run", validate_transition(previous, tampered))

    def test_initial_receipt_must_be_started(self):
        self.assertIn("first receipt state must be started", validate_transition(None, terminal("aborted")))


class HeartbeatTests(unittest.TestCase):
    def test_valid_heartbeat(self):
        heartbeat = {
            "schema_version": 1,
            "run_id": receipt()["run_id"],
            "receipt_state": "started",
            "sequence": 4,
            "monotonic_ns": 123456789,
            "written_at_utc": "2026-08-29T10:00:04.000Z",
            "started_receipt_sha256": SHA,
        }
        self.assertEqual([], validate_heartbeat(heartbeat))
        heartbeat["receipt_state"] = "valid_pass"
        self.assertIn("heartbeat.receipt_state must be started", validate_heartbeat(heartbeat))


class ManifestTests(unittest.TestCase):
    def test_live_manifest_requires_recovery_and_telemetry_evidence(self):
        manifest = {
            "schema_version": 1,
            "run_id": receipt()["run_id"],
            "generated_at_utc": "2026-08-29T10:15:01.000Z",
            "artifacts": [
                {"path": path, "role": role, "byte_count": 1, "sha256": SHA}
                for path, role in (
                    ("input_manifest.json", "input_manifest"),
                    ("receipt.json", "receipt"),
                    ("heartbeat.json", "heartbeat"),
                    ("telemetry.jsonl", "telemetry"),
                    ("diagnostics.json", "diagnostics"),
                    ("SHA256SUMS", "checksums"),
                )
            ],
        }
        self.assertEqual([], validate_artifact_manifest(manifest, channel="live_soak"))
        manifest["artifacts"] = [entry for entry in manifest["artifacts"] if entry["role"] != "heartbeat"]
        self.assertIn(
            "live_soak artifact heartbeat.json with role heartbeat is required",
            validate_artifact_manifest(manifest, channel="live_soak"),
        )

    def test_replay_manifest_requires_hashed_contract_artifacts(self):
        manifest = {
            "schema_version": 1,
            "run_id": receipt()["run_id"],
            "generated_at_utc": "2026-08-29T10:15:01.000Z",
            "artifacts": [
                {"path": path, "role": role, "byte_count": 1, "sha256": SHA}
                for path, role in (
                    ("input_manifest.json", "input_manifest"),
                    ("poses.tum", "poses"),
                    ("receipt.json", "receipt"),
                    ("heartbeat.json", "heartbeat"),
                    ("diagnostics.json", "diagnostics"),
                    ("SHA256SUMS", "checksums"),
                )
            ],
        }
        self.assertEqual([], validate_artifact_manifest(manifest, channel="replay_paced"))
        del manifest["artifacts"][1]["sha256"]
        self.assertIn("artifacts[1].sha256 is required", validate_artifact_manifest(manifest, channel="replay_paced"))

    def test_manifest_rejects_unsafe_or_duplicate_paths(self):
        manifest = {
            "schema_version": 1,
            "run_id": receipt()["run_id"],
            "generated_at_utc": "2026-08-29T10:15:01.000Z",
            "artifacts": [
                {"path": "../receipt.json", "role": "receipt", "byte_count": 1, "sha256": SHA},
                {"path": "../receipt.json", "role": "other", "byte_count": 1, "sha256": SHA},
            ],
        }
        errors = validate_artifact_manifest(manifest, channel="live_soak")
        self.assertIn("artifacts[0].path must be a safe relative path", errors)
        self.assertIn("artifact paths must be unique", errors)

    def test_manifest_role_enum_includes_finalized_diagnostics_and_rejects_unknown(self):
        manifest = {
            "schema_version": 1,
            "run_id": receipt()["run_id"],
            "generated_at_utc": "2026-08-29T10:15:01.000Z",
            "artifacts": [
                {
                    "path": "diagnostics.json",
                    "role": "diagnostics",
                    "byte_count": 1,
                    "sha256": SHA,
                }
            ],
        }
        self.assertEqual([], validate_artifact_manifest(manifest))
        manifest["artifacts"][0]["role"] = "invented"
        self.assertIn(
            "artifacts[0].role is not recognized",
            validate_artifact_manifest(manifest),
        )

    def test_manifest_can_verify_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = b"immutable input\n"
            (base / "input_manifest.json").write_bytes(payload)
            manifest = {
                "schema_version": 1,
                "run_id": receipt()["run_id"],
                "generated_at_utc": "2026-08-29T10:15:01.000Z",
                "artifacts": [{
                    "path": "input_manifest.json",
                    "role": "input_manifest",
                    "byte_count": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }],
            }
            self.assertEqual([], validate_artifact_manifest(manifest, base_directory=base))
            manifest["artifacts"][0]["sha256"] = SHA
            self.assertIn(
                "artifacts[0].sha256 does not match file bytes",
                validate_artifact_manifest(manifest, base_directory=base),
            )


class MetricDefinitionTests(unittest.TestCase):
    def test_frozen_catalog_defines_every_receipt_metric(self):
        document = json.loads(METRIC_DEFINITIONS.read_text())
        self.assertEqual([], validate_metric_definitions(document))
        defined = set(document["metrics"])
        used = set(terminal("valid_pass")["metrics"])
        used |= set(terminal("valid_pass", "replay_max")["metrics"])
        self.assertTrue(used <= defined)
        self.assertEqual("must_be_null_without_external_calibrated_analyzer", document["metrics"]["power_w"]["availability"])


if __name__ == "__main__":
    unittest.main()
