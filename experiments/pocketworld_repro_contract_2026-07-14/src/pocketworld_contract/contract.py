from __future__ import annotations

import json
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
    _validate_commercial_gate(document)


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
    if item["commercial_gate_included"] is True and (
        item["license_status"] != "verified_commercial_open_source"
        or contains_noncommercial is not False
    ):
        raise ContractError(
            "commercial gate inclusion requires verified commercial open-source license "
            f"and clean lineage: {item['evidence_id']}"
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
        ):
            raise ContractError(
                "commercial evaluation candidate requires every used model to have immutable "
                "source, revision, weight hash, license evidence hash, and verified commercial "
                "open-source license"
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
