from __future__ import annotations

import json
import math
import operator
import re
from collections.abc import Callable, Iterator, Mapping
from functools import lru_cache
from importlib.resources import files as resource_files

from jsonschema import Draft202012Validator

from pocketworld_contract.manifest import ContractError, safe_relative_path

_UNKNOWN_PLACEHOLDERS = frozenset({"unknown", "tbd", "todo"})
_TRANSIENT_PATH_MARKERS = (
    "/private/tmp",
    "/var/mobile/Containers",
    "/private/var/mobile/Containers",
)
_DVC_OID_PATTERN = re.compile(r"(?:md5:[0-9a-f]{32}(?:\.dir)?|sha256:[0-9a-f]{64})\Z")
_VERDICT_INPUT_ROLE = "verdict_input"
_VERDICT_OUTPUT_ROLE = "verdict_output"
_INCREMENTAL_BA_REVISION = "0a8b8428fba3fbf942af01ada6d1e1252a677c6a"
_THRESHOLD_OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema_resource = resource_files("pocketworld_contract").joinpath(
        "schemas/contract-v1.schema.json"
    )
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_contract(document: Mapping[str, object]) -> None:
    """Validate schema and fail-closed semantic gates for a research contract."""
    errors = sorted(_validator().iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ContractError(f"contract schema error at {location}: {error.message}")

    deviations = document["deviations"]
    assert isinstance(deviations, list)  # Guaranteed by the checked schema.
    deviation_fields = {
        deviation["field"]
        for deviation in deviations
        if isinstance(deviation, dict) and isinstance(deviation.get("field"), str)
    }
    null_paths = set(_walk_matching_values(document, lambda value: value is None))
    undocumented_nulls = sorted(null_paths - deviation_fields)
    if undocumented_nulls:
        raise ContractError(
            f"null truth requires an exact structured deviation: {undocumented_nulls[0]}"
        )

    placeholder_paths = sorted(
        _walk_matching_values(
            document,
            lambda value: (
                isinstance(value, str) and value.strip().casefold() in _UNKNOWN_PLACEHOLDERS
            ),
        )
    )
    if placeholder_paths:
        raise ContractError(
            "unknown truth must be null with a deviation, not a placeholder: "
            f"{placeholder_paths[0]}"
        )

    status = document["status"]
    verdict = document["verdict"]
    assert isinstance(verdict, dict)  # Guaranteed by the checked schema.
    eligible = verdict["eligible"]
    blockers = verdict["blockers"]
    blocking_deviations = [
        deviation
        for deviation in deviations
        if isinstance(deviation, dict) and deviation.get("blocks_verdict") is True
    ]
    if status == "verdict_eligible":
        if eligible is not True or blockers or blocking_deviations or null_paths:
            raise ContractError(
                "verdict_eligible requires no blockers, blocking deviations, or null truth"
            )
    elif eligible is not False:
        raise ContractError(f"contract status {status!r} cannot claim an eligible verdict")

    _validate_runnable_paths(document)
    _validate_unique_ids(document)
    _validate_execution_references(document)
    _validate_verdict_closure(document)
    _validate_metric_closure(document)
    _validate_evidence_identity(document)
    _validate_model_dependency_closure(document)
    _validate_replay_qualification(document)
    _validate_commercial_gate(document)


def _validate_unique_ids(document: Mapping[str, object]) -> None:
    evidence = [*document["collections"], *document["artifacts"]]
    surfaces = (
        ("evidence", evidence, "evidence_id"),
        ("metric", document["metrics"]["definitions"], "metric_id"),
        ("code", document["code"]["entries"], "code_id"),
        ("model", document["models"], "model_id"),
        (
            "dependency",
            document["product_qualification"]["dependencies"],
            "dependency_id",
        ),
        ("deviation", document["deviations"], "deviation_id"),
        ("exclusion", document["exclusions"], "exclusion_id"),
        ("stopping rule", document["stopping_rules"], "rule_id"),
    )
    for label, items, identifier_key in surfaces:
        identifiers = [item[identifier_key] for item in items]
        if len(identifiers) != len(set(identifiers)):
            raise ContractError(f"duplicate {label} identifier; IDs must be unique")


def _validate_execution_references(document: Mapping[str, object]) -> None:
    dependencies = {
        item["dependency_id"] for item in document["product_qualification"]["dependencies"]
    }
    code_entries = {item["code_id"]: item for item in document["code"]["entries"]}
    model_ids = {item["model_id"] for item in document["models"]}
    for entry in code_entries.values():
        missing = set(entry["dependency_ids"]) - dependencies
        if missing:
            raise ContractError(
                "code entry references undefined product dependency: "
                f"{entry['code_id']} / {sorted(missing)[0]}"
            )

    command = document["command"]
    if command["status"] != "known":
        return
    missing_code = set(command["code_ids"]) - set(code_entries)
    if missing_code:
        raise ContractError(f"command references undefined code entry: {sorted(missing_code)[0]}")
    runnable_code = {
        code_id
        for code_id, entry in code_entries.items()
        if entry["execution_status"] == "runnable"
    }
    if set(command["code_ids"]) != runnable_code:
        raise ContractError("known command must reference every and only runnable code entry")
    if command["config_id"] != document["effective_config"]["config_id"]:
        raise ContractError("command references an undefined effective config")
    missing_dependencies = set(command["dependency_ids"]) - dependencies
    if missing_dependencies:
        raise ContractError(
            f"command references undefined product dependency: {sorted(missing_dependencies)[0]}"
        )
    missing_models = set(command["model_ids"]) - model_ids
    if missing_models:
        raise ContractError(f"command references undefined model: {sorted(missing_models)[0]}")
    if set(command["model_ids"]) != model_ids:
        raise ContractError("known command must reference every declared used model")


def _validate_metric_closure(document: Mapping[str, object]) -> None:
    metrics = document["metrics"]
    definitions = {item["metric_id"] for item in metrics["definitions"]}
    evidence = {
        item["evidence_id"]: item for item in [*document["collections"], *document["artifacts"]]
    }
    _validate_metric_threshold_references(metrics, definitions, evidence)
    observed_pairs = _validate_metric_observations(metrics, definitions, evidence)

    if document["status"] == "verdict_eligible":
        _validate_verdict_threshold_results(document, metrics, observed_pairs)


def _validate_metric_threshold_references(
    metrics: Mapping[str, object],
    definitions: set[object],
    evidence: Mapping[str, object],
) -> None:
    for threshold in metrics["thresholds"]:
        metric_id = threshold["metric_id"]
        if metric_id not in definitions:
            raise ContractError(f"metric threshold references undefined metric: {metric_id}")
        value = threshold["value"]
        if not _is_finite_number(value):
            raise ContractError(f"metric threshold must be finite: {metric_id}")
        artifact_id = threshold.get("artifact_id")
        if artifact_id is not None and artifact_id not in evidence:
            raise ContractError(f"metric threshold references undefined artifact: {artifact_id}")


def _validate_metric_observations(
    metrics: Mapping[str, object],
    definitions: set[object],
    evidence: Mapping[str, object],
) -> set[tuple[object, object]]:
    pairs: set[tuple[object, object]] = set()
    for observation in metrics["observed"]:
        metric_id = observation["metric_id"]
        artifact_id = observation["artifact_id"]
        if metric_id not in definitions:
            raise ContractError(f"metric observation references undefined metric: {metric_id}")
        if artifact_id not in evidence:
            raise ContractError(f"metric observation references undefined artifact: {artifact_id}")
        value = observation["value"]
        if isinstance(value, float) and not math.isfinite(value):
            raise ContractError(f"metric observation must be finite: {metric_id}")
        pair = (metric_id, artifact_id)
        if pair in pairs:
            raise ContractError(
                "duplicate metric observation reference; metric/artifact pairs must be unique"
            )
        pairs.add(pair)
    return pairs


def _validate_verdict_threshold_results(
    document: Mapping[str, object],
    metrics: Mapping[str, object],
    observed_pairs: set[tuple[object, object]],
) -> None:
    observations = {(item["metric_id"], item["artifact_id"]): item for item in metrics["observed"]}
    results: list[bool] = []
    threshold_pairs: set[tuple[object, object]] = set()
    for threshold in metrics["thresholds"]:
        artifact_id = threshold.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise ContractError("verdict threshold closure requires an explicit artifact_id")
        pair = (threshold["metric_id"], artifact_id)
        if pair in threshold_pairs:
            raise ContractError(
                "duplicate verdict threshold metric/artifact pair; each threshold requires "
                "a unique observation"
            )
        threshold_pairs.add(pair)
        if pair not in observed_pairs:
            raise ContractError(
                "verdict threshold has no matching metric/artifact observation: "
                f"{threshold['metric_id']} / {artifact_id}"
            )
        observed = observations[pair]["value"]
        expected = threshold["value"]
        if not _is_finite_number(observed):
            raise ContractError(
                "verdict threshold observation must be a finite numeric value: "
                f"{threshold['metric_id']}"
            )
        comparator = _THRESHOLD_OPERATORS[threshold["operator"]]
        results.append(comparator(observed, expected))

    expected_decision = "pass" if all(results) else "fail"
    if document["verdict"]["decision"] != expected_decision:
        raise ContractError(
            "verdict decision conflicts with evaluated threshold results: "
            f"expected {expected_decision}"
        )


def _validate_evidence_identity(document: Mapping[str, object]) -> None:
    for item in [*document["collections"], *document["artifacts"]]:
        path = item["path"]
        if isinstance(path, str):
            try:
                safe_relative_path(path)
            except ContractError as exc:
                raise ContractError(
                    f"evidence path must be safe and repository-relative: {item['evidence_id']}"
                ) from exc
        dvc_oid = item["dvc_oid"]
        if isinstance(dvc_oid, str) and _DVC_OID_PATTERN.fullmatch(dvc_oid) is None:
            raise ContractError(f"evidence DVC OID is malformed: {item['evidence_id']}")


def _validate_model_dependency_closure(document: Mapping[str, object]) -> None:
    dependencies = {
        item["dependency_id"]: item for item in document["product_qualification"]["dependencies"]
    }
    for model in document["models"]:
        model_dependency_id = model["model_dependency_id"]
        model_dependency = dependencies.get(model_dependency_id)
        if model_dependency is None or model_dependency["kind"] != "model":
            raise ContractError(
                f"model must reference a product dependency of kind model: {model['model_id']}"
            )
        for dataset_id in model["training_dataset_dependency_ids"]:
            dependency = dependencies.get(dataset_id)
            if dependency is None or dependency["kind"] != "dataset":
                raise ContractError(
                    f"model must reference every training dataset dependency: {model['model_id']}"
                )
        for runtime_id in model["runtime_dependency_ids"]:
            dependency = dependencies.get(runtime_id)
            if dependency is None or dependency["kind"] not in {"source_code", "tool"}:
                raise ContractError(
                    "model runtime dependency must reference source_code or tool evidence: "
                    f"{model['model_id']}"
                )
        for key in (
            "source",
            "revision",
            "license_evidence_sha256",
            "license_status",
            "audit_verdict",
            "intended_use",
            "obligations",
        ):
            if model[key] != model_dependency[key]:
                raise ContractError(
                    "model identity must be backed by its referenced model dependency: "
                    f"{model['model_id']} ({key})"
                )
        model_license_path = model.get("license_evidence_path")
        if model_license_path is not None and model_license_path != model_dependency.get(
            "license_evidence_path"
        ):
            raise ContractError(
                f"model license evidence path must match its model dependency: {model['model_id']}"
            )


def _validate_verdict_closure(document: Mapping[str, object]) -> None:
    if document["status"] != "verdict_eligible":
        return
    if document["validation_scope"] != "decision_contract":
        raise ContractError("verdict_eligible requires validation_scope decision_contract")

    _validate_nonempty_verdict_surfaces(document)
    _validate_runnable_verdict_surfaces(document)
    _validate_verdict_evidence_closure(document)


def _validate_nonempty_verdict_surfaces(document: Mapping[str, object]) -> None:

    required_lists = {
        "collections": document["collections"],
        "artifacts": document["artifacts"],
        "code": document["code"]["entries"],
        "metric definitions": document["metrics"]["definitions"],
        "metric thresholds": document["metrics"]["thresholds"],
        "metric observations": document["metrics"]["observed"],
        "stopping rules": document["stopping_rules"],
    }
    for name, items in required_lists.items():
        if not items:
            raise ContractError(f"verdict closure requires nonempty {name}")


def _validate_runnable_verdict_surfaces(document: Mapping[str, object]) -> None:
    if any(entry["execution_status"] != "runnable" for entry in document["code"]["entries"]):
        raise ContractError("verdict closure requires every code entry to be runnable")
    if document["effective_config"]["status"] != "runnable":
        raise ContractError("verdict closure requires runnable effective config")
    if document["command"]["status"] != "known":
        raise ContractError("verdict closure requires a known command")


def _validate_verdict_evidence_closure(document: Mapping[str, object]) -> None:
    collections = document["collections"]
    artifacts = document["artifacts"]
    inputs = [item for item in collections if item["evidence_role"] == _VERDICT_INPUT_ROLE]
    outputs = [item for item in artifacts if item["evidence_role"] == _VERDICT_OUTPUT_ROLE]
    if not inputs or not outputs:
        raise ContractError("verdict closure requires verdict_input and verdict_output evidence")
    for item in [*inputs, *outputs]:
        _require_complete_verdict_evidence(item)

    output_by_id = {item["evidence_id"]: item for item in outputs}
    observed_output_ids = [item["artifact_id"] for item in document["metrics"]["observed"]]
    for output_id in observed_output_ids:
        output = output_by_id.get(output_id)
        if output is None or output["identity_status"] != "preserved":
            raise ContractError("every observation must reference a preserved verdict_output")


def _require_complete_verdict_evidence(item: Mapping[str, object]) -> None:
    required = (
        "path",
        "bytes",
        "sha256",
        "dvc_oid",
        "producer",
        "consumer",
        "platform_qualification",
        "evidence_role",
    )
    if item["identity_status"] != "preserved" or any(
        item[field] is None or item[field] == "" for field in required
    ):
        raise ContractError(
            "verdict evidence requires preserved full bytes/SHA/DVC/producer/consumer/"
            f"platform/role identity: {item['evidence_id']}"
        )
    dvc_oid = item["dvc_oid"]
    assert isinstance(dvc_oid, str)
    digest = dvc_oid.split(":", maxsplit=1)[1].removesuffix(".dir")
    if dvc_oid.endswith(".dir") or set(digest) == {"0"}:
        raise ContractError(
            f"verdict evidence requires a real single-file DVC OID: {item['evidence_id']}"
        )


def _validate_replay_qualification(document: Mapping[str, object]) -> None:
    qualification = document["replay_qualification"]
    is_replay = document["contract_kind"] == "replay_fixture"
    if is_replay != (qualification["applicable"] is True):
        raise ContractError(
            "replay_fixture contract kind and typed replay qualification must agree"
        )
    if not is_replay:
        return

    _reject_untyped_replay_truth(document)
    evidence = {
        item["evidence_id"]: item for item in [*document["collections"], *document["artifacts"]]
    }
    typed_refs = _validate_replay_evidence_refs(qualification, evidence)
    _validate_replay_component_bindings(evidence, typed_refs)
    if document["status"] == "verdict_eligible":
        _validate_replay_verdict(document, qualification, evidence, typed_refs)


def _reject_untyped_replay_truth(document: Mapping[str, object]) -> None:

    typed_only_fields = {
        "fresh_authorized_pull",
        "fresh_device_pull",
        "pull_timestamp",
        "source_device_id",
        "source_app_id",
        "source_app_revision",
        "source_app_revision_proven",
        "source_capture_directory",
        "ledger_capture_directory",
        "source_quiescence_proven",
        "consistent_backup_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "replay_identity_included",
        "algorithm_revision",
        "incremental_global_ba_default_enabled",
        "control_variable",
        "control_off_value",
        "control_on_value",
        "only_control_variable_difference_proven",
    }
    for item in [*document["collections"], *document["artifacts"]]:
        duplicated = sorted(typed_only_fields & set(item["details"]))
        if duplicated:
            raise ContractError(
                "replay critical truth must use typed replay_qualification/evidence fields, "
                f"not details: {item['evidence_id']} ({duplicated[0]})"
            )


def _validate_replay_evidence_refs(
    qualification: Mapping[str, object],
    evidence: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    typed_refs = {
        "db": qualification["db_evidence_id"],
        "WAL": qualification["wal_evidence_id"],
        "pose": qualification["pose_evidence_id"],
        "SHM": qualification["shm_evidence_id"],
    }
    referenced_ids = [evidence_id for evidence_id in typed_refs.values() if evidence_id is not None]
    if len(referenced_ids) != len(set(referenced_ids)):
        raise ContractError("replay component evidence references must be pairwise distinct")
    for label, evidence_id in typed_refs.items():
        if evidence_id is not None and evidence_id not in evidence:
            raise ContractError(f"replay {label} evidence reference is undefined: {evidence_id}")

    shm_id = qualification["shm_evidence_id"]
    if shm_id is not None:
        shm = evidence[shm_id]
        if (
            shm["identity_status"] != "excluded_volatile"
            or shm["replay_identity_included"] is not False
        ):
            raise ContractError("replay SHM must be excluded_volatile and excluded from identity")
    return typed_refs


def _validate_replay_verdict(
    document: Mapping[str, object],
    qualification: Mapping[str, object],
    evidence: Mapping[str, Mapping[str, object]],
    typed_refs: Mapping[str, object],
) -> None:
    _require_replay_proofs(qualification)
    _validate_replay_control_identity(qualification)
    _validate_replay_capture_identity(document, qualification)
    _validate_replay_input_evidence(evidence, typed_refs)


def _validate_replay_component_bindings(
    evidence: Mapping[str, Mapping[str, object]],
    typed_refs: Mapping[str, object],
) -> None:
    expected_kinds = {
        "db": "sqlite_database",
        "WAL": "sqlite_wal",
        "pose": "pose_jsonl",
        "SHM": "sqlite_shm",
    }
    for label, expected_kind in expected_kinds.items():
        evidence_id = typed_refs[label]
        if evidence_id is None:
            continue
        assert isinstance(evidence_id, str)
        if evidence[evidence_id].get("replay_component_kind") != expected_kind:
            raise ContractError(
                f"replay {label} evidence must declare component kind {expected_kind}"
            )


def _require_replay_proofs(qualification: Mapping[str, object]) -> None:
    required_true = (
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    )
    if any(qualification[key] is not True for key in required_true):
        raise ContractError(
            "replay verdict requires a fresh authorized device pull, proven app revision, "
            "capture binding, atomic DB/WAL, integrity, DB/pose alignment, and a single "
            "control-variable difference"
        )
    if not (
        qualification["source_quiescence_proven"] is True
        or qualification["consistent_backup_proven"] is True
    ):
        raise ContractError("replay verdict requires source quiescence or a consistent backup")


def _validate_replay_capture_identity(
    document: Mapping[str, object],
    qualification: Mapping[str, object],
) -> None:
    required_identity = (
        "pull_timestamp",
        "source_device_id",
        "source_app_id",
        "source_app_revision",
        "source_capture_directory",
        "ledger_capture_directory",
        "db_evidence_id",
        "wal_evidence_id",
        "pose_evidence_id",
        "shm_evidence_id",
    )
    if any(not qualification[key] for key in required_identity):
        raise ContractError("replay verdict requires complete typed capture and app identity")
    if qualification["source_capture_directory"] != qualification["ledger_capture_directory"]:
        raise ContractError("replay DB and pose ledger must bind to the same capture directory")
    if (
        qualification["fixture_contract_id"] != document["contract_id"]
        or "provisional" in document["contract_id"].casefold()
    ):
        raise ContractError("replay verdict requires a new immutable non-provisional contract ID")


def _validate_replay_control_identity(qualification: Mapping[str, object]) -> None:
    if qualification["algorithm_revision"] != _INCREMENTAL_BA_REVISION:
        raise ContractError("replay verdict requires the clean 0a8b8428 incremental-BA revision")
    if qualification["incremental_global_ba_default_enabled"] is not False:
        raise ContractError("incremental global BA must remain default-off until the verdict")
    expected_control = {
        "control_variable": "AETHER_INCREMENTAL_GLOBAL_BA",
        "control_off_value": "unset",
        "control_on_value": "1",
    }
    if any(qualification[key] != value for key, value in expected_control.items()):
        raise ContractError(
            "replay verdict requires the exact incremental-BA OFF/ON control identity"
        )


def _validate_replay_input_evidence(
    evidence: Mapping[str, Mapping[str, object]],
    typed_refs: Mapping[str, object],
) -> None:
    for label in ("db", "WAL", "pose"):
        evidence_id = typed_refs[label]
        assert isinstance(evidence_id, str)
        item = evidence[evidence_id]
        if (
            item["identity_status"] != "preserved"
            or item["evidence_role"] != _VERDICT_INPUT_ROLE
            or item["replay_identity_included"] is not True
        ):
            raise ContractError(f"replay {label} must be a preserved replay-identity verdict_input")


def _validate_runnable_paths(document: Mapping[str, object]) -> None:
    _validate_effective_config_paths(document)
    _validate_code_paths(document)
    _validate_command_paths(document)


def _validate_effective_config_paths(document: Mapping[str, object]) -> None:
    effective_config = document["effective_config"]
    assert isinstance(effective_config, dict)
    if effective_config["status"] == "runnable":
        config_path = effective_config["path"]
        if not isinstance(config_path, str):
            raise ContractError("runnable effective_config requires a repository-relative path")
        try:
            safe_relative_path(config_path)
        except ContractError as exc:
            raise ContractError(
                "runnable effective_config path must be repository-relative"
            ) from exc
        transient = _first_transient_string(effective_config["values"])
        if transient is not None:
            raise ContractError(
                f"runnable effective_config contains a transient absolute path: {transient}"
            )


def _validate_code_paths(document: Mapping[str, object]) -> None:
    code = document["code"]
    assert isinstance(code, dict)
    for entry in code["entries"]:
        assert isinstance(entry, dict)
        if entry["execution_status"] == "runnable":
            code_path = entry["path"]
            if not isinstance(code_path, str):
                raise ContractError("runnable code entry requires a repository-relative path")
            try:
                safe_relative_path(code_path)
            except ContractError as exc:
                raise ContractError("runnable code path must be repository-relative") from exc
            transient = _first_transient_string(entry)
            if transient is not None:
                raise ContractError(f"runnable code contains a transient path: {transient}")


def _validate_command_paths(document: Mapping[str, object]) -> None:
    command = document["command"]
    assert isinstance(command, dict)
    if command["status"] == "known":
        cwd = command["cwd"]
        argv = command["argv"]
        assert isinstance(cwd, str)
        assert isinstance(argv, list)
        if cwd != ".":
            try:
                safe_relative_path(cwd)
            except ContractError as exc:
                raise ContractError("known command cwd must be repository-relative") from exc
        transient = _first_transient_string(command)
        if transient is not None:
            raise ContractError(f"known command contains a transient mobile path: {transient}")


def _first_transient_string(value: object) -> str | None:
    for _path, string in _walk_strings(value):
        normalized = string.replace("\\", "/")
        if any(marker in normalized for marker in _TRANSIENT_PATH_MARKERS):
            return string
    return None


def _walk_strings(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path or "/", value
    elif isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}/{index}")


def _validate_commercial_gate(document: Mapping[str, object]) -> None:
    evidence_items = [*document["collections"], *document["artifacts"]]
    for item in evidence_items:
        assert isinstance(item, dict)
        _validate_evidence_commercial_gate(item)

    product_qualification = document["product_qualification"]
    assert isinstance(product_qualification, dict)
    dependencies = product_qualification["dependencies"]
    for dependency in dependencies:
        assert isinstance(dependency, dict)
        _validate_product_dependency_lineage(dependency)
    if product_qualification["status"] == "commercial_evaluation_candidate":
        _validate_commercial_candidate(document, product_qualification, dependencies)


def _validate_evidence_commercial_gate(item: Mapping[str, object]) -> None:
    contains_noncommercial = item["lineage_contains_noncommercial"]
    lineage_sources = item["noncommercial_lineage_sources"]
    if contains_noncommercial is True and not lineage_sources:
        raise ContractError(f"noncommercial lineage requires named sources: {item['evidence_id']}")
    if contains_noncommercial is False and lineage_sources:
        raise ContractError(
            f"commercial lineage flag conflicts with named sources: {item['evidence_id']}"
        )
    if contains_noncommercial is None and lineage_sources:
        raise ContractError(f"unknown lineage cannot claim named sources: {item['evidence_id']}")
    if item["commercial_gate_included"] is not True:
        return
    if item["identity_status"] != "preserved" or contains_noncommercial is not False:
        raise ContractError(
            "commercial gate inclusion requires preserved evidence with clean lineage: "
            f"{item['evidence_id']}"
        )
    license_status = item["license_status"]
    if license_status == "verified_commercial_open_source":
        if not item.get("license_evidence_sha256"):
            raise ContractError(
                "included open-source evidence requires a license evidence SHA-256: "
                f"{item['evidence_id']}"
            )
    elif license_status in {"user_owned_private_input", "user_owned_derived_output"}:
        if not item.get("rights_basis") or not item.get("rights_evidence_sha256"):
            raise ContractError(
                "included user-owned evidence requires rights_basis and rights evidence SHA-256: "
                f"{item['evidence_id']}"
            )
    else:
        raise ContractError(
            "commercial gate inclusion requires verified commercial open source or documented "
            f"user-owned rights with clean lineage: {item['evidence_id']}"
        )


def _validate_product_dependency_lineage(dependency: Mapping[str, object]) -> None:
    contains_noncommercial = dependency["lineage_contains_noncommercial"]
    lineage_sources = dependency["noncommercial_lineage_sources"]
    if contains_noncommercial is True and not lineage_sources:
        raise ContractError(
            "noncommercial product dependency lineage requires named sources: "
            f"{dependency['dependency_id']}"
        )
    if contains_noncommercial is False and lineage_sources:
        raise ContractError(
            "product dependency lineage flag conflicts with named sources: "
            f"{dependency['dependency_id']}"
        )
    if contains_noncommercial is None and lineage_sources:
        raise ContractError(
            "unknown product dependency lineage cannot claim named sources: "
            f"{dependency['dependency_id']}"
        )


def _validate_commercial_candidate(
    document: Mapping[str, object],
    product_qualification: Mapping[str, object],
    dependencies: list[object],
) -> None:
    if document["status"] != "verdict_eligible":
        raise ContractError("commercial evaluation candidate requires a generic eligible verdict")
    if product_qualification["commercial_open_source_dependencies_verified"] is not True:
        raise ContractError(
            "commercial evaluation candidate requires verified open-source dependencies"
        )
    if product_qualification["execution_dependency_closure_declared_complete"] is not True:
        raise ContractError(
            "commercial evaluation candidate requires an explicitly complete execution "
            "dependency closure"
        )
    if not dependencies:
        raise ContractError(
            "commercial evaluation candidate requires a nonempty dependency evidence list"
        )
    _validate_commercial_dependency_evidence(dependencies)

    dependency_by_id = {dependency["dependency_id"]: dependency for dependency in dependencies}
    referenced_dependencies = _commercial_execution_dependency_ids(document, dependency_by_id)
    declared_dependencies = set(dependency_by_id)
    if referenced_dependencies != declared_dependencies:
        missing = declared_dependencies - referenced_dependencies
        extra = referenced_dependencies - declared_dependencies
        detail = sorted(missing or extra)[0]
        raise ContractError(
            "commercial dependency closure contains an unreferenced or undefined dependency: "
            f"{detail}"
        )
    _validate_commercial_model_evidence(document["models"])
    _validate_commercial_verdict_evidence(document)


def _validate_commercial_dependency_evidence(dependencies: list[object]) -> None:
    for dependency in dependencies:
        assert isinstance(dependency, dict)
        required_evidence = (
            dependency["source"],
            dependency["revision"],
            dependency["license_identifier"],
            dependency.get("license_evidence_path"),
            dependency["license_evidence_sha256"],
        )
        if (
            any(value is None for value in required_evidence)
            or dependency["license_status"] != "verified_commercial_open_source"
            or dependency["audit_verdict"] != "allow"
            or dependency["lineage_contains_noncommercial"] is not False
        ):
            raise ContractError(
                "commercial evaluation candidate requires complete, verified dependency "
                f"license evidence: {dependency['dependency_id']}"
            )
        _require_safe_commercial_path(
            dependency["license_evidence_path"],
            f"dependency license evidence: {dependency['dependency_id']}",
        )


def _validate_commercial_model_evidence(models: list[object]) -> None:
    for model in models:
        assert isinstance(model, dict)
        model_identity = (
            model["source"],
            model["revision"],
            model.get("weights_path"),
            model["weights_sha256"],
            model.get("license_evidence_path"),
            model["license_evidence_sha256"],
        )
        if (
            any(value is None for value in model_identity)
            or model["license_status"] != "verified_commercial_open_source"
            or model["audit_verdict"] != "allow"
        ):
            raise ContractError(
                "commercial evaluation candidate requires every used model to have immutable "
                "source, revision, weight hash, license evidence hash, and verified commercial "
                "open-source license"
            )
        _require_safe_commercial_path(model["weights_path"], f"model weights: {model['model_id']}")
        _require_safe_commercial_path(
            model["license_evidence_path"],
            f"model license evidence: {model['model_id']}",
        )


def _validate_commercial_verdict_evidence(document: Mapping[str, object]) -> None:
    verdict_inputs = [
        item for item in document["collections"] if item["evidence_role"] == _VERDICT_INPUT_ROLE
    ]
    included_inputs = [
        item
        for item in verdict_inputs
        if item["commercial_gate_included"] is True and item["identity_status"] == "preserved"
    ]
    included_outputs = [
        item
        for item in document["artifacts"]
        if item["evidence_role"] == _VERDICT_OUTPUT_ROLE
        and item["commercial_gate_included"] is True
        and item["identity_status"] == "preserved"
    ]
    if not verdict_inputs or len(included_inputs) != len(verdict_inputs) or not included_outputs:
        raise ContractError(
            "commercial candidate requires every verdict_input and an observed verdict_output "
            "to be included, preserved commercial-gate evidence"
        )
    included_output_ids = {item["evidence_id"] for item in included_outputs}
    observed_output_ids = {item["artifact_id"] for item in document["metrics"]["observed"]}
    if not observed_output_ids <= included_output_ids:
        raise ContractError(
            "every commercially observed verdict output must be included in the commercial gate"
        )


def _commercial_execution_dependency_ids(
    document: Mapping[str, object],
    dependency_by_id: Mapping[str, Mapping[str, object]],
) -> set[str]:
    command = document["command"]
    command_dependencies = set(command["dependency_ids"])
    if not command_dependencies:
        raise ContractError("commercial command execution requires nonempty dependency IDs")
    _require_dependency_kinds(
        command_dependencies,
        dependency_by_id,
        allowed={"source_code", "tool"},
        label="command execution",
    )
    referenced = set(command_dependencies)
    for entry in document["code"]["entries"]:
        dependencies = set(entry["dependency_ids"])
        if entry["execution_status"] == "runnable" and not dependencies:
            raise ContractError(
                f"commercial runnable code requires nonempty dependency IDs: {entry['code_id']}"
            )
        _require_dependency_kinds(
            dependencies,
            dependency_by_id,
            allowed={"source_code", "tool"},
            label=f"code entry {entry['code_id']}",
        )
        referenced.update(dependencies)

    models = {model["model_id"]: model for model in document["models"]}
    if set(command["model_ids"]) != set(models):
        raise ContractError(
            "commercial command must explicitly reference every and only used model"
        )
    model_dependency_counts: dict[str, int] = {}
    training_dataset_dependencies: set[str] = set()
    for model in models.values():
        model_dependency_id = model["model_dependency_id"]
        model_dependency_counts[model_dependency_id] = (
            model_dependency_counts.get(model_dependency_id, 0) + 1
        )
        training_ids = set(model["training_dataset_dependency_ids"])
        training_dataset_dependencies.update(training_ids)
        referenced.add(model_dependency_id)
        referenced.update(training_ids)
        referenced.update(model["runtime_dependency_ids"])

    for dependency_id, dependency in dependency_by_id.items():
        if dependency["kind"] == "model" and model_dependency_counts.get(dependency_id, 0) != 1:
            raise ContractError(
                "commercial model dependency must be backed by exactly one model record: "
                f"{dependency_id}"
            )
        if dependency["kind"] == "dataset" and dependency_id not in training_dataset_dependencies:
            raise ContractError(
                "commercial dataset dependency must be referenced through a model training "
                f"dataset slot: {dependency_id}"
            )
    return referenced


def _require_dependency_kinds(
    dependency_ids: set[str],
    dependency_by_id: Mapping[str, Mapping[str, object]],
    *,
    allowed: set[str],
    label: str,
) -> None:
    for dependency_id in dependency_ids:
        if dependency_by_id[dependency_id]["kind"] not in allowed:
            raise ContractError(
                f"commercial dependency kind is not allowed in {label}: {dependency_id}"
            )


def _require_safe_commercial_path(path: object, label: str) -> None:
    if not isinstance(path, str):
        raise ContractError(f"commercial {label} requires a repository-relative path")
    try:
        safe_relative_path(path)
    except ContractError as exc:
        raise ContractError(
            f"commercial {label} must be repository-relative and rehashable"
        ) from exc


def _walk_matching_values(
    value: object,
    predicate: Callable[[object], bool],
    path: str = "",
) -> Iterator[str]:
    if predicate(value):
        yield path or "/"
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from _walk_matching_values(child, predicate, f"{path}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_matching_values(child, predicate, f"{path}/{index}")
