#!/usr/bin/env python3
"""Freeze the unified three-arm bench source and built-artifact identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "BasaltVIOBench.xcodeproj",
    "VIOReplacementBench.xcodeproj",
    "_build",
    "_vcpkg_installed",
    "basalt",
    "basalt-headers",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


def normalized_git_status(repo: Path, excluded_paths: set[str]) -> str:
    lines = git(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    normalized = []
    for line in lines:
        path_field = line[3:] if len(line) >= 4 else ""
        if path_field in excluded_paths:
            continue
        normalized.append(line)
    return "\n".join(normalized)


def included(path: Path, tool_root: Path) -> bool:
    relative = path.relative_to(tool_root)
    if path.name == "source_manifest.json" or path.suffix == ".pyc":
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    return path.is_file()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path)
    parser.add_argument("--basalt-framework", type=Path)
    parser.add_argument("--xrslam-framework", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()

    tool_root = Path(__file__).resolve().parents[1]
    repo = Path(git(tool_root, "rev-parse", "--show-toplevel"))
    output_path = args.output.resolve()
    output_relative = str(output_path.relative_to(repo))
    status_exclusions = {output_relative}

    if args.verify_existing:
        document = json.loads(output_path.read_text(encoding="utf-8"))
        failures: list[str] = []
        if document.get("repository_base_head") != git(repo, "rev-parse", "HEAD"):
            failures.append("repository_base_head")
        if document.get("branch") != git(repo, "branch", "--show-current"):
            failures.append("branch")
        recorded_exclusions = set(document.get("working_tree_status_exclusions", []))
        if recorded_exclusions != status_exclusions:
            failures.append("working_tree_status_exclusions")
        status_hash = hashlib.sha256(
            normalized_git_status(repo, status_exclusions).encode()
        ).hexdigest()
        if document.get("working_tree_status_sha256") != status_hash:
            failures.append("working_tree_status_sha256")
        for item in document.get("files", []):
            path = repo / item["path"]
            if not path.is_file() or path.stat().st_size != item["bytes"] \
                    or sha256(path) != item["sha256"]:
                failures.append(f"file:{item['path']}")
        for name, item in document.get("build_artifacts", {}).items():
            path = Path(item["path"])
            if not path.is_file() or path.stat().st_size != item["bytes"] \
                    or sha256(path) != item["sha256"]:
                failures.append(f"build_artifact:{name}")
        if failures:
            raise SystemExit("source manifest verification failed: " + ", ".join(failures))
        print("source manifest verification passed")
        return

    if args.app is None or args.basalt_framework is None or args.xrslam_framework is None:
        parser.error("--app, --basalt-framework, and --xrslam-framework are required unless --verify-existing is used")
    selected = [
        path for path in tool_root.rglob("*") if included(path, tool_root)
    ]
    selected.extend((repo / relative) for relative in (
        "docs/plans/2026-08-29-basalt-ios-vio-bench-design.md",
        "docs/plans/2026-08-29-basalt-ios-vio-bench-implementation.md",
        "experiments/basalt_vio_phone_bench_2026-08-29/contract.json",
        "openspec/changes/add-dual-vio-phone-bench/design.md",
        "openspec/changes/add-dual-vio-phone-bench/proposal.md",
        "openspec/changes/add-dual-vio-phone-bench/tasks.md",
    ))
    selected = sorted(set(path.resolve() for path in selected if path.is_file()))

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_head": git(repo, "rev-parse", "HEAD"),
        "branch": git(repo, "branch", "--show-current"),
        "working_tree_status_exclusions": sorted(status_exclusions),
        "working_tree_status_sha256": hashlib.sha256(
            normalized_git_status(repo, status_exclusions).encode()
        ).hexdigest(),
        "files": [
            {
                "path": str(path.relative_to(repo)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in selected
        ],
        "build_artifacts": {
            "unified_app_binary": {
                "path": str(args.app),
                "bytes": args.app.stat().st_size,
                "sha256": sha256(args.app),
            },
            "basalt_framework_binary": {
                "path": str(args.basalt_framework),
                "bytes": args.basalt_framework.stat().st_size,
                "sha256": sha256(args.basalt_framework),
            },
            "xrslam_framework_binary": {
                "path": str(args.xrslam_framework),
                "bytes": args.xrslam_framework.stat().st_size,
                "sha256": sha256(args.xrslam_framework),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
