from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path


PYTHON_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_TOOLS))

import b0_run_monitored as monitored
import b0_preregister as prereg


GIB = 1024**3
CODE_ROOT = PYTHON_TOOLS.parents[1]


class SequenceProbe:
    def __init__(self, *values: monitored.ProbeResult) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self, *_args: object) -> monitored.ProbeResult:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


def known(value: int, **details: object) -> monitored.ProbeResult:
    return monitored.ProbeResult.known(value, details=details)


def unknown(message: str) -> monitored.ProbeResult:
    return monitored.ProbeResult.unknown(message)


class MonitoredRunnerTests(unittest.TestCase):
    def _run(
        self,
        root: Path,
        command: list[str],
        *,
        name: str = "run",
        disk_probe=None,
        rss_probe=None,
        swap_probe=None,
        timeout: float = 2.0,
        rss_limit: int = 12 * GIB,
        sample_interval: float = 0.02,
        resource_poll: float = 0.01,
        preregistered_contract: Path | None = None,
        phase: str | None = None,
        attest_files: tuple[Path, ...] = (),
        attest_trees: tuple[Path, ...] = (),
        require_prior_statuses: tuple[Path, ...] = (),
    ) -> dict[str, object]:
        return monitored.run_monitored(
            command,
            resource_log=root / name / "resources.ndjson",
            status_path=root / name / "status.json",
            disk_path=root,
            label="unit-test",
            env_allowlist=("PATH",),
            env_overrides={"B0_TEST_VISIBLE": "yes"},
            sample_interval_seconds=sample_interval,
            resource_poll_seconds=resource_poll,
            wall_timeout_seconds=timeout,
            disk_probe=disk_probe or (lambda _path: known(20 * GIB)),
            rss_probe=rss_probe or (lambda _pid: known(1024, process_count=1)),
            swap_probe=swap_probe or (lambda: known(2 * GIB)),
            peak_rss_bytes=rss_limit,
            termination_grace_seconds=0.05,
            preregistered_contract=preregistered_contract,
            phase=phase,
            attest_files=attest_files,
            attest_trees=attest_trees,
            require_prior_statuses=require_prior_statuses,
        )

    def test_success_records_logs_hashes_samples_and_allowlisted_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [
                sys.executable,
                "-c",
                (
                    "import os,sys; "
                    "print(os.environ.get('B0_TEST_VISIBLE')); "
                    "print('err-line', file=sys.stderr)"
                ),
            ]

            result = self._run(root, command)

            out = root / "run"
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(result["exit_code"], 0)
            self.assertIsNotNone(result["timing"]["command_started_at_utc"])
            self.assertGreaterEqual(
                result["timing"]["wrapper_wall_seconds"], result["wall_seconds"]
            )
            self.assertEqual((out / "status.stdout.log").read_text(), "yes\n")
            self.assertEqual((out / "status.stderr.log").read_text(), "err-line\n")
            self.assertEqual(
                result["logs"]["stdout"]["sha256"],
                hashlib.sha256(b"yes\n").hexdigest(),
            )
            self.assertEqual(
                result["logs"]["stderr"]["sha256"],
                hashlib.sha256(b"err-line\n").hexdigest(),
            )
            self.assertEqual(result["command"]["argv"], command)
            self.assertIn("PATH", result["environment"]["effective"])
            self.assertEqual(result["environment"]["effective"]["B0_TEST_VISIBLE"], "yes")
            self.assertNotIn("SHELL", result["environment"]["effective"])
            samples = [
                json.loads(line)
                for line in (out / "resources.ndjson").read_text().splitlines()
            ]
            self.assertGreaterEqual(len(samples), 2)
            self.assertEqual(samples[0]["phase"], "preflight")
            self.assertEqual(samples[-1]["phase"], "end")
            self.assertEqual(
                json.loads((out / "status.json").read_text()), result
            )

    def test_refuses_existing_output_without_running_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            out.mkdir()
            (out / "status.json").write_text("existing")
            marker = root / "marker"

            with self.assertRaises(FileExistsError):
                monitored.run_monitored(
                    [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
                    resource_log=out / "resources.ndjson",
                    status_path=out / "status.json",
                    disk_path=root,
                )

            self.assertFalse(marker.exists())

    def test_preflight_rejects_when_free_disk_is_below_fifteen_gib(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "marker"
            result = self._run(
                root,
                [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
                disk_probe=lambda _path: known(15 * GIB - 1),
            )

            self.assertEqual(result["verdict"], "DISK_GUARD")
            self.assertFalse(result["started"])
            self.assertIsNone(result["exit_code"])
            self.assertIsNone(result["wall_seconds"])
            self.assertFalse(marker.exists())

    def test_runtime_disk_guard_terminates_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disk = SequenceProbe(known(20 * GIB), known(5 * GIB), known(5 * GIB))

            started = time.monotonic()
            result = self._run(
                root,
                [sys.executable, "-c", "import time; time.sleep(30)"],
                disk_probe=disk,
            )

            self.assertLess(time.monotonic() - started, 3.0)
            self.assertEqual(result["verdict"], "DISK_GUARD")
            self.assertTrue(result["termination"]["process_group_signalled"])
            self.assertLess(result["resources"]["disk"]["minimum_available_bytes"], 6 * GIB)

    def test_wall_timeout_has_timeout_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=0.05,
            )

            self.assertEqual(result["verdict"], "TIMEOUT")
            self.assertGreaterEqual(result["wall_seconds"], 0.04)

    def test_known_disk_breach_takes_precedence_at_timeout_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            disk = SequenceProbe(known(20 * GIB), known(5 * GIB), known(5 * GIB))
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", "import time; time.sleep(30)"],
                disk_probe=disk,
                timeout=0.000001,
            )

            self.assertEqual(result["verdict"], "DISK_GUARD")
            self.assertEqual(result["termination"]["trigger"], "disk_limit")

    def test_actual_allocating_child_trips_process_tree_rss_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_program = "payload=bytearray(64*1024*1024); import time; time.sleep(30)"
            parent_program = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable, '-c', {child_program!r}]); "
                "time.sleep(30)"
            )
            result = self._run(
                Path(tmp),
                [
                    sys.executable,
                    "-c",
                    parent_program,
                ],
                rss_probe=monitored.probe_process_tree_rss,
                rss_limit=30 * 1024**2,
            )

            self.assertEqual(result["verdict"], "RESOURCE_GUARD")
            self.assertEqual(result["termination"]["trigger"], "rss_limit")
            self.assertGreater(
                result["resources"]["rss"]["peak_bytes"], 30 * 1024**2
            )
            self.assertGreaterEqual(
                result["resources"]["rss"]["max_process_count"], 2
            )
            self.assertFalse(
                result["termination"]["process_group_alive_at_status"]
            )

    def test_short_memory_peak_is_caught_between_disk_heartbeats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child_program = (
                "import time; payload=bytearray(64*1024*1024); "
                "time.sleep(0.12); del payload; time.sleep(0.4)"
            )
            parent_program = (
                "import subprocess,sys; "
                f"subprocess.run([sys.executable, '-c', {child_program!r}])"
            )
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", parent_program],
                rss_probe=monitored.probe_process_tree_rss,
                rss_limit=30 * 1024**2,
                sample_interval=0.8,
                resource_poll=0.01,
            )

            self.assertEqual(result["verdict"], "RESOURCE_GUARD")
            self.assertEqual(result["termination"]["trigger"], "rss_limit")
            self.assertLess(result["wall_seconds"], 0.8)
            self.assertGreaterEqual(result["resource_poll_count"], 2)
            self.assertEqual(result["heartbeat_count"], 1)
            self.assertEqual(result["timing"]["resource_poll_seconds"], 0.01)

    def test_stable_high_frequency_polls_do_not_bloat_ndjson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", "import time; time.sleep(0.08)"],
                sample_interval=0.2,
                resource_poll=0.01,
            )

            self.assertEqual(result["verdict"], "PASS")
            self.assertGreaterEqual(result["resource_poll_count"], 5)
            self.assertEqual(result["heartbeat_count"], 1)
            self.assertLessEqual(result["samples_count"], 4)

    def test_swap_growth_above_four_gib_trips_resource_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            swap = SequenceProbe(known(1 * GIB), known(6 * GIB), known(6 * GIB))
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", "import time; time.sleep(30)"],
                swap_probe=swap,
            )

            self.assertEqual(result["verdict"], "RESOURCE_GUARD")
            self.assertEqual(result["termination"]["trigger"], "swap_growth_limit")
            self.assertGreater(result["resources"]["swap"]["peak_growth_bytes"], 4 * GIB)

    def test_unreadable_swap_is_unknown_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp),
                [sys.executable, "-c", "pass"],
                swap_probe=lambda: unknown("sysctl unavailable"),
            )

            self.assertEqual(result["verdict"], "UNKNOWN")
            self.assertEqual(result["command_outcome"], "SUCCESS")
            self.assertEqual(result["resources"]["swap"]["status"], "UNKNOWN")
            self.assertIn("sysctl unavailable", result["resources"]["swap"]["errors"])

    def test_nonzero_child_exit_is_recorded_as_command_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                Path(tmp), [sys.executable, "-c", "raise SystemExit(17)"]
            )

            self.assertEqual(result["verdict"], "COMMAND_FAILED")
            self.assertEqual(result["command_outcome"], "FAILED")
            self.assertEqual(result["exit_code"], 17)

    def test_success_attests_new_file_and_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_file = root / "mesh.obj"
            output_tree = root / "export"
            command = [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    f"Path({str(output_file)!r}).write_bytes(b'mesh'); "
                    f"Path({str(output_tree)!r}).mkdir(); "
                    f"Path({str(output_tree / 'depth.exr')!r}).write_bytes(b'depth')"
                ),
            ]

            result = self._run(
                root,
                command,
                attest_files=(output_file,),
                attest_trees=(output_tree,),
            )

            self.assertEqual(result["verdict"], "PASS")
            attestation = result["attestation"]
            self.assertEqual(attestation["status"], "VERIFIED")
            self.assertEqual(attestation["files"][0]["size_bytes"], 4)
            self.assertEqual(attestation["trees"][0]["file_count"], 1)
            self.assertEqual(
                attestation["trees"][0]["files"][0]["relative_path"],
                "depth.exr",
            )

    def test_missing_or_symlink_attestation_is_nonpass(self) -> None:
        for mode in ("missing", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / "mesh.obj"
                replacement = root / "replacement.obj"
                if mode == "missing":
                    code = "pass"
                else:
                    replacement.write_bytes(b"mesh")
                    code = (
                        "from pathlib import Path; "
                        f"Path({str(target)!r}).symlink_to({str(replacement)!r})"
                    )
                result = self._run(
                    root,
                    [sys.executable, "-c", code],
                    attest_files=(target,),
                )
                self.assertEqual(result["verdict"], "ATTESTATION_FAILED")
                self.assertEqual(result["attestation"]["status"], "FAILED")

    def test_failed_child_does_not_attest_even_if_it_wrote_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "partial.obj"
            command = [
                sys.executable,
                "-c",
                f"open({str(target)!r}, 'wb').write(b'partial'); raise SystemExit(9)",
            ]

            result = self._run(root, command, attest_files=(target,))

            self.assertEqual(result["verdict"], "COMMAND_FAILED")
            self.assertEqual(result["attestation"]["status"], "SKIPPED_CHILD_FAILED")
            self.assertEqual(result["attestation"]["files"], [])

    def test_prior_status_revalidates_attested_file_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "export.bin"
            first = self._run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"open({str(artifact)!r}, 'wb').write(b'frozen')",
                ],
                name="first",
                attest_files=(artifact,),
            )
            prior = Path(first["logs"]["resources"]["path"]).with_name(
                "status.json"
            )
            marker = root / "second-started"
            second = self._run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"open({str(marker)!r}, 'w').close()",
                ],
                name="second",
                require_prior_statuses=(prior,),
            )
            self.assertEqual(second["verdict"], "PASS")
            self.assertTrue(marker.exists())
            self.assertEqual(second["prior_statuses"][0]["status"], "VERIFIED")

    def test_modified_replaced_or_missing_prior_artifact_blocks_prelaunch(self) -> None:
        for mode in ("modified", "replaced", "missing"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                artifact = root / "export.bin"
                first = self._run(
                    root,
                    [
                        sys.executable,
                        "-c",
                        f"open({str(artifact)!r}, 'wb').write(b'frozen')",
                    ],
                    name="first",
                    attest_files=(artifact,),
                )
                prior = Path(first["logs"]["resources"]["path"]).with_name(
                    "status.json"
                )
                if mode == "modified":
                    artifact.write_bytes(b"changed")
                elif mode == "replaced":
                    replacement = root / "replacement.bin"
                    replacement.write_bytes(b"frozen")
                    artifact.unlink()
                    artifact.symlink_to(replacement)
                else:
                    artifact.unlink()
                marker = root / "must-not-start"

                with self.assertRaises(monitored.PriorStatusError):
                    self._run(
                        root,
                        [
                            sys.executable,
                            "-c",
                            f"open({str(marker)!r}, 'w').close()",
                        ],
                        name="second",
                        require_prior_statuses=(prior,),
                    )
                self.assertFalse(marker.exists())
                self.assertFalse((root / "second").exists())

    def test_modified_prior_attested_tree_blocks_prelaunch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_tree = root / "export"
            artifact_file = artifact_tree / "depth.exr"
            first = self._run(
                root,
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(artifact_tree)!r}).mkdir(); "
                        f"Path({str(artifact_file)!r}).write_bytes(b'frozen')"
                    ),
                ],
                name="first",
                attest_trees=(artifact_tree,),
            )
            prior = Path(first["logs"]["resources"]["path"]).with_name(
                "status.json"
            )
            artifact_file.write_bytes(b"changed")
            marker = root / "must-not-start"

            with self.assertRaises(monitored.PriorStatusError):
                self._run(
                    root,
                    [
                        sys.executable,
                        "-c",
                        f"open({str(marker)!r}, 'w').close()",
                    ],
                    name="second",
                    require_prior_statuses=(prior,),
                )
            self.assertFalse(marker.exists())
            self.assertFalse((root / "second").exists())

    def test_preexisting_attestation_target_is_rejected_before_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "already-there.obj"
            target.write_bytes(b"old")
            marker = root / "must-not-start"

            with self.assertRaises(monitored.ConfigurationError):
                self._run(
                    root,
                    [
                        sys.executable,
                        "-c",
                        f"open({str(marker)!r}, 'w').close()",
                    ],
                    attest_files=(target,),
                )
            self.assertFalse(marker.exists())
            self.assertFalse((root / "run").exists())

    def test_guarded_run_skips_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "must-not-exist.obj"
            result = self._run(
                root,
                [
                    sys.executable,
                    "-c",
                    f"open({str(target)!r}, 'w').close()",
                ],
                disk_probe=lambda _path: known(5 * GIB),
                attest_files=(target,),
            )

            self.assertEqual(result["verdict"], "DISK_GUARD")
            self.assertEqual(result["attestation"]["status"], "SKIPPED_NON_SUCCESS")
            self.assertFalse(target.exists())


class ProbeParserTests(unittest.TestCase):
    def test_parse_macos_swapusage(self) -> None:
        value = monitored.parse_swapusage_bytes(
            "vm.swapusage: total = 8192.00M  used = 5120.50M  free = 3071.50M"
        )
        self.assertEqual(value, int(5120.5 * 1024**2))

    def test_process_tree_parser_sums_root_and_descendants_only(self) -> None:
        listing = "1 0 100\n10 1 200\n11 10 300\n20 1 400\n21 999 500\n"
        rss, count = monitored.process_tree_rss_from_ps(listing, root_pid=10)
        self.assertEqual(rss, (200 + 300) * 1024)
        self.assertEqual(count, 2)

    def test_cli_rejects_monitor_interval_over_thirty_minutes(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "test",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--sample-interval-seconds",
                "1800.1",
                "--",
                "/usr/bin/true",
            ]
        )
        with self.assertRaises(monitored.ConfigurationError):
            monitored.validate_cli_args(args)


class FormalBindingTests(unittest.TestCase):
    def _write_contract(
        self,
        root: Path,
        child_argv: list[str],
        *,
        phase: str = "tsdf_meshing",
        mutate=None,
    ) -> tuple[Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        binary = root / "aliceVision_meshing"
        binary.write_bytes(b"fixture executable\n")
        binary.chmod(0o755)
        identity = deepcopy(
            prereg._freeze_execution_identity(
                code_root=CODE_ROOT,
                alicevision_binary=binary,
            )
        )
        contract = {
            "schema_version": "b0-preregistration-v1",
            "frozen_authority": identity,
            "execution_plan": {
                "formal_runner_bindings": {
                    phase: {
                        "child_argv": child_argv,
                        "child_argv_sha256": monitored._canonical_sha256(
                            child_argv
                        ),
                    }
                }
            },
        }
        if mutate is not None:
            mutate(contract)
        path = root / "contract.json"
        path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        path.with_suffix(".sha256").write_text(
            f"{monitored._sha256_file(path)}  {path.name}\n",
            encoding="utf-8",
        )
        return path, binary

    def _run_bound(
        self,
        root: Path,
        command: list[str],
        contract: Path,
        *,
        phase: str = "tsdf_meshing",
        require_prior_statuses: tuple[Path, ...] = (),
    ) -> dict[str, object]:
        return monitored.run_monitored(
            command,
            resource_log=root / "run" / "resources.ndjson",
            status_path=root / "run" / "status.json",
            disk_path=root,
            label="formal-binding-test",
            env_allowlist=monitored.DEFAULT_ENV_ALLOWLIST,
            sample_interval_seconds=0.02,
            resource_poll_seconds=0.01,
            wall_timeout_seconds=2.0,
            disk_probe=lambda _path: known(20 * GIB),
            rss_probe=lambda _pid: known(1024, process_count=1),
            swap_probe=lambda: known(2 * GIB),
            preregistered_contract=contract,
            phase=phase,
            require_prior_statuses=require_prior_statuses,
        )

    def test_valid_formal_binding_runs_and_records_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable, "-c", "print('bound')"]
            contract, _ = self._write_contract(root, command)

            result = self._run_bound(root, command, contract)

            self.assertEqual(result["verdict"], "PASS")
            binding = result["formal_binding"]
            self.assertEqual(binding["status"], "VERIFIED")
            self.assertEqual(binding["phase"], "tsdf_meshing")
            self.assertEqual(binding["contract_path"], str(contract.resolve()))
            self.assertEqual(
                binding["child_argv_sha256"],
                monitored._canonical_sha256(command),
            )

    def test_child_argv_mismatch_fails_before_output_or_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "marker"
            expected = [sys.executable, "-c", "pass"]
            actual = [
                sys.executable,
                "-c",
                f"open({str(marker)!r}, 'w').close()",
            ]
            contract, _ = self._write_contract(root, expected)

            with self.assertRaises(monitored.FormalBindingError):
                self._run_bound(root, actual, contract)

            self.assertFalse(marker.exists())
            self.assertFalse((root / "run").exists())

    def test_source_and_binary_drift_each_fail_before_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable, "-c", "pass"]

            def mutate_source(contract: dict[str, object]) -> None:
                files = contract["frozen_authority"]["source_state"][
                    "dirty_code_bundle"
                ]["files"]
                files[0]["size_bytes"] += 1

            source_contract, _ = self._write_contract(
                root / "source", command, mutate=mutate_source
            )
            with self.assertRaises(monitored.FormalBindingError):
                self._run_bound(root / "source", command, source_contract)
            self.assertFalse((root / "source" / "run").exists())

            binary_root = root / "binary"
            binary_root.mkdir()
            binary_contract, binary = self._write_contract(binary_root, command)
            binary.write_bytes(binary.read_bytes() + b"drift")
            with self.assertRaises(monitored.FormalBindingError):
                self._run_bound(binary_root, command, binary_contract)
            self.assertFalse((binary_root / "run").exists())

    def test_python_module_environment_drift_fails_before_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable, "-c", "pass"]

            def mutate_environment(contract: dict[str, object]) -> None:
                environment = contract["frozen_authority"]["environment_identity"]
                environment["identity"]["required_python_modules"]["numpy"][
                    "version"
                ] = "drifted-version"
                environment["sha256"] = monitored._canonical_sha256(
                    environment["identity"]
                )

            contract, _ = self._write_contract(
                root, command, mutate=mutate_environment
            )
            with self.assertRaises(monitored.FormalBindingError):
                self._run_bound(root, command, contract)
            self.assertFalse((root / "run").exists())

    def test_phase_missing_or_placeholder_argv_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable, "-c", "pass"]
            contract, _ = self._write_contract(root, ["<CHILD>"])
            with self.assertRaises(monitored.FormalBindingError):
                self._run_bound(root, command, contract)
            self.assertFalse((root / "run").exists())

    def test_formal_run_rejects_unbound_prior_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "export.bin"
            monitored.run_monitored(
                [
                    sys.executable,
                    "-c",
                    f"open({str(artifact)!r}, 'wb').write(b'frozen')",
                ],
                resource_log=root / "prior" / "resources.ndjson",
                status_path=root / "prior" / "status.json",
                disk_path=root,
                env_allowlist=("PATH",),
                sample_interval_seconds=0.02,
                resource_poll_seconds=0.01,
                disk_probe=lambda _path: known(20 * GIB),
                rss_probe=lambda _pid: known(1024, process_count=1),
                swap_probe=lambda: known(2 * GIB),
                attest_files=(artifact,),
            )
            command = [sys.executable, "-c", "pass"]
            contract, _ = self._write_contract(root / "formal", command)

            with self.assertRaises(monitored.PriorStatusError):
                self._run_bound(
                    root / "formal",
                    command,
                    contract,
                    require_prior_statuses=(root / "prior" / "status.json",),
                )
            self.assertFalse((root / "formal" / "run").exists())

    def test_cli_requires_contract_and_phase_together_and_absolute(self) -> None:
        parser = monitored.build_parser()
        common = [
            "--label",
            "test",
            "--resource-log",
            "/tmp/resources.ndjson",
            "--status",
            "/tmp/status.json",
            "--disk-path",
            "/",
        ]
        for binding_args in (
            ["--preregistered-contract", "/tmp/contract.json"],
            ["--phase", "tsdf_meshing"],
            [
                "--preregistered-contract",
                "relative-contract.json",
                "--phase",
                "tsdf_meshing",
            ],
        ):
            with self.subTest(binding_args=binding_args):
                args = parser.parse_args(
                    common + binding_args + ["--", "/usr/bin/true"]
                )
                with self.assertRaises(monitored.ConfigurationError):
                    monitored.validate_cli_args(args)

    def test_cli_accepts_exact_preregistered_option_names(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "cap100-tsdf",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--start-available-gib",
                "15",
                "--stop-available-gib",
                "6",
                "--sample-interval-seconds",
                "1800",
                "--peak-rss-gib",
                "12",
                "--swap-growth-gib",
                "4",
                "--wall-time-seconds",
                "14400",
                "--",
                "/usr/bin/true",
            ]
        )
        command, overrides = monitored.validate_cli_args(args)
        self.assertEqual(command, ["/usr/bin/true"])
        self.assertEqual(overrides, {})
        self.assertEqual(args.start_available_gib, 15.0)
        self.assertEqual(args.stop_available_gib, 6.0)
        self.assertEqual(args.peak_rss_gib, 12.0)
        self.assertEqual(args.swap_growth_gib, 4.0)
        self.assertEqual(args.wall_time_seconds, 14400.0)
        self.assertEqual(args.resource_poll_seconds, 1.0)

    def test_cli_accepts_explicit_one_second_resource_poll(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "cap100-tsdf",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--sample-interval-seconds",
                "1800",
                "--resource-poll-seconds",
                "1",
                "--",
                "/usr/bin/true",
            ]
        )
        command, _ = monitored.validate_cli_args(args)
        self.assertEqual(command, ["/usr/bin/true"])

    def test_cli_accepts_repeatable_attestation_and_prior_options(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "test",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--attest-file",
                "/tmp/mesh.obj",
                "--attest-file",
                "/tmp/mesh.mtl",
                "--attest-tree",
                "/tmp/export",
                "--require-prior-status",
                "/tmp/export-status.json",
                "--",
                "/usr/bin/true",
                "--attest-file",
                "child-value",
            ]
        )

        command, _ = monitored.validate_cli_args(args)

        self.assertEqual(
            command,
            ["/usr/bin/true", "--attest-file", "child-value"],
        )
        self.assertEqual(len(args.attest_file), 2)
        self.assertEqual(len(args.attest_tree), 1)
        self.assertEqual(len(args.require_prior_status), 1)

    def test_cli_rejects_relative_attestation_and_prior_paths(self) -> None:
        parser = monitored.build_parser()
        common = [
            "--label",
            "test",
            "--resource-log",
            "/tmp/resources.ndjson",
            "--status",
            "/tmp/status.json",
            "--disk-path",
            "/",
        ]
        for option in (
            "--attest-file",
            "--attest-tree",
            "--require-prior-status",
        ):
            with self.subTest(option=option):
                args = parser.parse_args(
                    common + [option, "relative-path", "--", "/usr/bin/true"]
                )
                with self.assertRaises(monitored.ConfigurationError):
                    monitored.validate_cli_args(args)

    def test_cli_rejects_resource_poll_over_five_seconds(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "test",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--sample-interval-seconds",
                "1800",
                "--resource-poll-seconds",
                "5.01",
                "--",
                "/usr/bin/true",
            ]
        )
        with self.assertRaises(monitored.ConfigurationError):
            monitored.validate_cli_args(args)

    def test_cli_rejects_resource_poll_slower_than_heartbeat(self) -> None:
        parser = monitored.build_parser()
        args = parser.parse_args(
            [
                "--label",
                "test",
                "--resource-log",
                "/tmp/resources.ndjson",
                "--status",
                "/tmp/status.json",
                "--disk-path",
                "/",
                "--sample-interval-seconds",
                "0.5",
                "--resource-poll-seconds",
                "1",
                "--",
                "/usr/bin/true",
            ]
        )
        with self.assertRaises(monitored.ConfigurationError):
            monitored.validate_cli_args(args)


if __name__ == "__main__":
    unittest.main()
