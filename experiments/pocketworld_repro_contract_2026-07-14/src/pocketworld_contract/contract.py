from __future__ import annotations

import json
import math
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


def _validate_metric_closure(document: Mapping[str, object]) -> None:
    metrics = document["metrics"]
    definitions = {item["metric_id"] for item in metrics["definitions"]}
    for threshold in metrics["thresholds"]:
        metric_id = threshold["metric_id"]
        if metric_id not in definitions:
            raise ContractError(f"metric threshold references undefined metric: {metric_id}")
        value = threshold["value"]
        if isinstance(value, bool) or not math.isfinite(value):
            raise ContractError(f"metric threshold must be finite: {metric_id}")

    evidence = {
        item["evidence_id"]: item for item in [*document["collections"], *document["artifacts"]]
    }
    observed_pairs: set[tuple[object, object]] = set()
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
        if pair in observed_pairs:
            raise ContractError(
                "duplicate metric observation reference; metric/artifact pairs must be unique"
            )
        observed_pairs.add(pair)


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
    if len(observed_output_ids) != len(set(observed_output_ids)):
        raise ContractError("each verdict output may back only one decision observation")
    for output_id in observed_output_ids:
        output = output_by_id.get(output_id)
        if output is None or output["identity_status"] != "preserved":
            raise ContractError(
                "every observation must reference a unique preserved verdict_output"
            )


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
    required_true = (
        "fresh_authorized_pull",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
    )
    if any(qualification[key] is not True for key in required_true):
        raise ContractError(
            "replay verdict requires fresh authorized pull, capture binding, atomic DB/WAL, "
            "integrity, and DB/pose alignment"
        )
    if not (
        qualification["source_quiescence_proven"] is True
        or qualification["consistent_backup_proven"] is True
    ):
        raise ContractError("replay verdict requires source quiescence or a consistent backup")
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
    if not dependencies:
        raise ContractError(
            "commercial evaluation candidate requires a nonempty dependency evidence list"
        )
    for dependency in dependencies:
        assert isinstance(dependency, dict)
        required_evidence = (
            dependency["source"],
            dependency["revision"],
            dependency["license_identifier"],
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
    for model in document["models"]:
        assert isinstance(model, dict)
        model_identity = (
            model["source"],
            model["revision"],
            model["weights_sha256"],
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

    included_inputs = [
        item
        for item in document["collections"]
        if item["evidence_role"] == _VERDICT_INPUT_ROLE
        and item["commercial_gate_included"] is True
        and item["identity_status"] == "preserved"
    ]
    included_outputs = [
        item
        for item in document["artifacts"]
        if item["evidence_role"] == _VERDICT_OUTPUT_ROLE
        and item["commercial_gate_included"] is True
        and item["identity_status"] == "preserved"
    ]
    if not included_inputs or not included_outputs:
        raise ContractError(
            "commercial candidate requires included preserved verdict_input and verdict_output"
        )
    included_output_ids = {item["evidence_id"] for item in included_outputs}
    observed_output_ids = {item["artifact_id"] for item in document["metrics"]["observed"]}
    if not observed_output_ids <= included_output_ids:
        raise ContractError(
            "every commercially observed verdict output must be included in the commercial gate"
        )


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
