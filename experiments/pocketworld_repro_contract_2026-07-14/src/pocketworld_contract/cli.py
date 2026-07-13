from __future__ import annotations

import argparse
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
            print("verdict_eligible")
        elif arguments.command == "verify-contract":
            validate_contract(_load_json_object(arguments.contract))
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
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ContractError(f"JSON document must be an object: {path}")
    return loaded
