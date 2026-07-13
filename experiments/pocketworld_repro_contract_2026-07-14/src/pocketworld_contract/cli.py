from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from contextlib import ExitStack, suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from pocketworld_contract.contract import validate_contract
from pocketworld_contract.manifest import (
    ContractError,
    build_collection,
    canonical_json,
    require_verdict_eligible,
    safe_relative_path,
    verify_collection,
)

_TEMP_NAME_ATTEMPTS = 128


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local PocketWorld asset contract CLI."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "build":
            root_descriptor, output_parent, output_name = _open_output_destination(
                arguments.root,
                arguments.output,
            )
            try:
                manifest = build_collection(
                    arguments.root,
                    arguments.collection,
                    license_status=arguments.license_status,
                    platform_qualification=arguments.platform_qualification,
                    evidence_role=arguments.evidence_role,
                    lineage_contains_noncommercial=arguments.lineage_contains_noncommercial,
                    _expected_root=os.fstat(root_descriptor),
                )
                _require_collection_root_pinned(arguments.root, root_descriptor)
                _require_output_parent_outside_collection(
                    root_descriptor,
                    output_parent,
                )
                _write_output_atomically(
                    arguments.root,
                    root_descriptor,
                    output_parent,
                    output_name,
                    canonical_json(manifest).encode("utf-8"),
                )
            finally:
                os.close(output_parent)
                os.close(root_descriptor)
        elif arguments.command == "verify":
            verify_collection(arguments.root, _load_json_object(arguments.manifest))
            print("verified")
        elif arguments.command == "gate-verdict":
            contract = _load_json_object(arguments.contract)
            validate_contract(contract)
            require_verdict_eligible(contract)
            _verify_repository_verdict_closure(arguments.contract, contract)
            print("verdict_eligible")
        elif arguments.command == "verify-contract":
            contract = _load_json_object(arguments.contract)
            validate_contract(contract)
            _verify_repository_verdict_closure(arguments.contract, contract)
            print("contract_verified")
        else:  # pragma: no cover - argparse restricts command choices.
            parser.error(f"unknown command: {arguments.command}")
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _open_output_destination(root: Path, output: Path) -> tuple[int, int, str]:
    output_name = output.name
    if output_name in {"", ".", ".."}:
        raise ContractError("build output must name a file")

    with ExitStack() as cleanup:
        root_descriptor = _open_directory(root, no_follow=True)
        cleanup.callback(os.close, root_descriptor)
        output_parent = _open_directory(output.parent, no_follow=False)
        cleanup.callback(os.close, output_parent)
        _require_output_parent_outside_collection(root_descriptor, output_parent)
        cleanup.pop_all()
    return root_descriptor, output_parent, output_name


def _require_output_parent_outside_collection(
    root_descriptor: int,
    output_parent: int,
) -> None:
    if _directory_is_within(output_parent, root_descriptor):
        raise ContractError("build output must be outside the collection root")


def _require_collection_root_pinned(root: Path, root_descriptor: int) -> None:
    try:
        current_path = root.lstat()
    except OSError as exc:
        raise ContractError("collection root changed before output publication") from exc
    opened = os.fstat(root_descriptor)
    if not stat.S_ISDIR(current_path.st_mode) or _file_identity(current_path) != _file_identity(
        opened
    ):
        raise ContractError("collection root changed before output publication")


def _open_directory(path: Path, *, no_follow: bool) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    if no_follow:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def _directory_is_within(directory_descriptor: int, root_descriptor: int) -> bool:
    root_identity = _file_identity(os.fstat(root_descriptor))
    current_descriptor = os.dup(directory_descriptor)
    try:
        while True:
            current_identity = _file_identity(os.fstat(current_descriptor))
            if current_identity == root_identity:
                return True
            parent_descriptor = os.open(
                "..",
                _directory_openat_flags(),
                dir_fd=current_descriptor,
            )
            parent_identity = _file_identity(os.fstat(parent_descriptor))
            if parent_identity == current_identity:
                os.close(parent_descriptor)
                return False
            os.close(current_descriptor)
            current_descriptor = parent_descriptor
    finally:
        os.close(current_descriptor)


def _directory_openat_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _file_identity(file_stat: os.stat_result) -> tuple[int, int]:
    return file_stat.st_dev, file_stat.st_ino


def _write_output_atomically(
    root: Path,
    root_descriptor: int,
    parent_descriptor: int,
    output_name: str,
    payload: bytes,
) -> None:
    temporary_name, temporary_descriptor = _create_temporary_output(parent_descriptor)
    try:
        try:
            _write_all(temporary_descriptor, payload)
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        _require_collection_root_pinned(root, root_descriptor)
        _require_output_parent_outside_collection(root_descriptor, parent_descriptor)
        os.replace(
            temporary_name,
            output_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = ""
        os.fsync(parent_descriptor)
    finally:
        if temporary_name:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=parent_descriptor)


def _create_temporary_output(parent_descriptor: int) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(_TEMP_NAME_ATTEMPTS):
        temporary_name = f".pocketworld-contract-{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(
                temporary_name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError:
            continue
        return temporary_name, descriptor
    raise ContractError("unable to allocate a unique temporary output file")


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written == 0:
            raise OSError("unable to write manifest output")
        view = view[written:]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pocketworld-contract")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="build a deterministic collection manifest")
    build_parser.add_argument("root", type=Path)
    build_parser.add_argument("--collection", required=True)
    build_parser.add_argument("--license-status", required=True)
    build_parser.add_argument("--platform-qualification", required=True)
    build_parser.add_argument("--evidence-role", required=True)
    build_parser.add_argument("--lineage-contains-noncommercial", action="store_true")
    build_parser.add_argument("--output", required=True, type=Path)

    verify_parser = subparsers.add_parser("verify", help="verify an exact collection manifest")
    verify_parser.add_argument("root", type=Path)
    verify_parser.add_argument("manifest", type=Path)

    gate_parser = subparsers.add_parser(
        "gate-verdict",
        help="require a verdict-eligible research contract",
    )
    gate_parser.add_argument("contract", type=Path)

    contract_parser = subparsers.add_parser(
        "verify-contract",
        help="validate a complete research contract and its fail-closed semantic gates",
    )
    contract_parser.add_argument("contract", type=Path)
    return parser


def _load_json_object(path: Path) -> Mapping[str, object]:
    raw = _read_pinned_regular_file(path)
    loaded = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_nonfinite_json_constant,
    )
    if not isinstance(loaded, dict):
        raise ContractError(f"JSON document must be an object: {path}")
    if raw != canonical_json(loaded).encode("utf-8"):
        raise ContractError(f"JSON document is not canonical: {path}")
    return loaded


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> object:
    raise ContractError(f"non-finite JSON number is forbidden: {value}")


def _read_pinned_regular_file(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ContractError(f"unable to inspect file: {path}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise ContractError(f"symlink is forbidden: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise ContractError(f"expected a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContractError(f"unable to open file safely: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _file_identity(before) != _file_identity(opened):
            raise ContractError(f"file changed before read: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 4 * 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = path.lstat()
    except OSError as exc:
        raise ContractError(f"file changed during read: {path}") from exc
    if not _same_regular_snapshot(before, opened, after, current):
        raise ContractError(f"file changed during read: {path}")
    return b"".join(chunks)


def _same_regular_snapshot(*states: os.stat_result) -> bool:
    first = states[0]
    identity = _file_identity(first)
    metadata = (first.st_size, first.st_mtime_ns, first.st_ctime_ns)
    return all(
        stat.S_ISREG(item.st_mode)
        and _file_identity(item) == identity
        and (item.st_size, item.st_mtime_ns, item.st_ctime_ns) == metadata
        for item in states[1:]
    )


def _verify_repository_verdict_closure(
    contract_path: Path,
    document: Mapping[str, object],
) -> None:
    if document.get("status") != "verdict_eligible":
        return
    repository_root = _find_repository_root(contract_path)
    for expectation in _repository_expected_files(document):
        _verify_expected_repository_file(repository_root, expectation)


def _repository_expected_files(
    document: Mapping[str, object],
) -> list[tuple[object, object, object, object]]:
    evidence = [*document["collections"], *document["artifacts"]]
    expected_files = [
        (item["path"], item["bytes"], item["sha256"], item["dvc_oid"])
        for item in evidence
        if (
            item["identity_status"] == "preserved"
            and item["evidence_role"] in {"verdict_input", "verdict_output"}
        )
    ]
    expected_files.extend(
        (entry["path"], None, entry["sha256"], None) for entry in document["code"]["entries"]
    )
    config = document["effective_config"]
    expected_files.append((config["path"], None, config["sha256"], None))
    verifier = document["environment"]["verifier"]
    expected_files.append((verifier["uv_lock_path"], None, verifier["uv_lock_sha256"], None))
    return expected_files


def _verify_expected_repository_file(
    repository_root: Path,
    expectation: tuple[object, object, object, object],
) -> None:
    relative_path, expected_bytes, expected_sha256, expected_dvc_oid = expectation
    if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
        raise ContractError("verdict closure contains incomplete repository file identity")
    safe_relative_path(relative_path)
    payload = _read_repo_relative_file(repository_root, relative_path)
    if expected_bytes is not None and len(payload) != expected_bytes:
        raise ContractError(f"verdict closure byte count mismatch: {relative_path}")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ContractError(f"verdict closure SHA-256 mismatch: {relative_path}")
    if expected_dvc_oid is None:
        return
    if not isinstance(expected_dvc_oid, str):
        raise ContractError(f"verdict closure has invalid DVC OID: {relative_path}")
    actual_dvc_oid = _dvc_oid_for_payload(payload, expected_dvc_oid)
    if actual_dvc_oid != expected_dvc_oid:
        raise ContractError(f"verdict closure DVC OID mismatch: {relative_path}")


def _find_repository_root(contract_path: Path) -> Path:
    try:
        start = contract_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"unable to resolve contract parent: {contract_path}") from exc
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if marker.exists() or marker.is_file():
            return candidate
    raise ContractError(f"contract is not inside a Git repository: {contract_path}")


def _read_repo_relative_file(repository_root: Path, relative_path: str) -> bytes:
    current = repository_root
    parts = relative_path.split("/")
    for component in parts[:-1]:
        current = current / component
        try:
            state = current.lstat()
        except OSError as exc:
            raise ContractError(f"verdict closure path is unavailable: {relative_path}") from exc
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
            raise ContractError(f"verdict closure path contains a symlink: {relative_path}")
    return _read_pinned_regular_file(current / parts[-1])


def _dvc_oid_for_payload(payload: bytes, expected: str) -> str:
    if expected.startswith("md5:"):
        suffix = ".dir" if expected.endswith(".dir") else ""
        digest = hashlib.md5(payload, usedforsecurity=False).hexdigest()
        return f"md5:{digest}{suffix}"
    if expected.startswith("sha256:"):
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"
    raise ContractError(f"unsupported DVC OID algorithm: {expected}")
