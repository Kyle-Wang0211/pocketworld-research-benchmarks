#!/usr/bin/env python3
"""Source-agnostic pre-birth controller for the first U2 experiment.

This controller consumes proposal records and already-frozen per-view evidence.
It does not know whether a proposal originated in B, D, SIFT, or a future
proposal generator.  A proposal is deferred only when reliable signed
free-space contradictions strictly outvote surface agreements.  Occlusion and
uninformative views abstain.

The experiment preserves the device baseline vertex payload byte-for-byte and
appends only proposals certified before a visible point identity is minted.
Nothing is deleted after publication.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any


PLY_RECORD = struct.Struct("<fffBBB")
EXPECTED_BASELINE_SHA256 = (
    "b1079c9984ca219ff2b97430e9f9a3cac9d3bfd02f7cd9255e42197091ada00b"
)
EXPECTED_PROPOSALS_SHA256 = (
    "4d3058ce8bacfebc8f8bc55d0ee97b65cee01ec70e937ea48f8782096d058359"
)
EXPECTED_EVIDENCE_SHA256 = (
    "36c957d82ef0a1421f03ba2d215dbcb79286ff52574a5df24e99489741aa6279"
)
EXPECTED_BASELINE_POINTS = 51_000
EXPECTED_PROPOSALS = 4_443
EXPECTED_CERTIFIED = 4_416
EXPECTED_DEFERRED = 27
CLASSIFICATIONS = (
    "ABSTAIN",
    "AGREEMENT",
    "FREE_SPACE_CONFLICT",
    "OCCLUDED_ABSTAIN",
)
PLY_PROPERTIES = (
    "property float x",
    "property float y",
    "property float z",
    "property uchar red",
    "property uchar green",
    "property uchar blue",
)
OUTPUT_NAMES = (
    "candidate_full.ply",
    "added_certified.ply",
    "deferred_only.ply",
    "decisions.jsonl",
    "manifest.json",
)


def decide_birth(*, agreement: int, free_space_conflict: int) -> str:
    """Return the single global lifecycle decision for one proposal."""
    if agreement < 0 or free_space_conflict < 0:
        raise ValueError("evidence counts must be non-negative")
    if free_space_conflict > agreement:
        return "DEFERRED"
    return "CERTIFIED"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ply(path: Path) -> tuple[bytes, int]:
    data = path.read_bytes()
    terminator = b"end_header\n"
    marker = data.find(terminator)
    if marker < 0:
        raise ValueError(f"{path}: missing PLY header terminator")
    header_end = marker + len(terminator)
    header = data[:header_end].decode("ascii")
    lines = header.splitlines()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise ValueError(f"{path}: unsupported PLY encoding")
    structural_lines = [
        line
        for line in lines
        if not line.startswith("comment ") and not line.startswith("obj_info ")
    ]
    vertices = [line for line in structural_lines if line.startswith("element vertex ")]
    if len(vertices) != 1:
        raise ValueError(f"{path}: expected one vertex element")
    count = int(vertices[0].split()[-1])
    expected_schema = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {count}",
        *PLY_PROPERTIES,
        "end_header",
    ]
    if structural_lines != expected_schema:
        raise ValueError(f"{path}: expected exact packed xyzrgb vertex schema")
    payload = data[header_end:]
    if len(payload) != count * PLY_RECORD.size:
        raise ValueError(f"{path}: expected packed 15-byte xyzrgb records")
    return payload, count


def make_ply(count: int, payload: bytes, comment: str) -> bytes:
    if len(payload) != count * PLY_RECORD.size:
        raise ValueError("PLY payload/count mismatch")
    return (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"comment {comment}\n"
        f"element vertex {count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii") + payload


def load_evidence(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row is not an object")
            rows.append(row)
    if len(rows) != EXPECTED_PROPOSALS:
        raise ValueError(f"expected {EXPECTED_PROPOSALS} evidence rows")
    indices = [int(row["birth_index"]) for row in rows]
    if sorted(indices) != list(range(EXPECTED_PROPOSALS)):
        raise ValueError("evidence birth_index is not a complete unique partition")
    return sorted(rows, key=lambda row: int(row["birth_index"]))


def validate_evidence_row(
    evidence: dict[str, Any],
    *,
    row_index: int,
) -> dict[str, int]:
    """Return exact evidence counts after rejecting omissions and unknowns."""
    claimed = evidence.get("class_counts")
    if not isinstance(claimed, dict):
        raise ValueError(f"evidence row {row_index}: missing class_counts")
    if set(claimed) != set(CLASSIFICATIONS):
        raise ValueError(
            f"evidence row {row_index}: class_counts must contain exactly "
            f"{CLASSIFICATIONS}"
        )
    counts: dict[str, int] = {}
    for classification in CLASSIFICATIONS:
        value = claimed[classification]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"evidence row {row_index}: invalid count for {classification}"
            )
        counts[classification] = value

    source_rows = evidence.get("source_evidence")
    if not isinstance(source_rows, list):
        raise ValueError(f"evidence row {row_index}: missing source evidence")
    observed = {classification: 0 for classification in CLASSIFICATIONS}
    for source_index, source in enumerate(source_rows):
        if not isinstance(source, dict):
            raise ValueError(
                f"evidence row {row_index}: source {source_index} is not an object"
            )
        classification = source.get("classification")
        if classification not in observed:
            raise ValueError(
                f"evidence row {row_index}: unknown classification "
                f"{classification!r}"
            )
        observed[classification] += 1
    if observed != counts or sum(counts.values()) != len(source_rows):
        raise ValueError(f"evidence row {row_index}: exact aggregate mismatch")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def file_identity(
    path: Path,
    *,
    reported_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "path": str((reported_path or path).resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def validate_output_layout(input_paths: tuple[Path, ...], output_dir: Path) -> None:
    """Reject overwrite, symlink, and canonical input/output collisions."""
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    input_resolved = {path.resolve(strict=True) for path in input_paths}
    output_resolved = {
        (output_dir / name).resolve(strict=False) for name in OUTPUT_NAMES
    }
    collisions = input_resolved & output_resolved
    if collisions:
        raise ValueError(f"input/output path collision: {sorted(map(str, collisions))}")


def publish_directory_no_replace(staging_dir: Path, output_dir: Path) -> None:
    """Atomically publish a complete directory without replacing any target."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "U2 research publication requires macOS renameatx_np RENAME_EXCL"
        )
    at_fdcwd = -2
    rename_excl = 0x00000004
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = libc.renameatx_np
    renameatx_np.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        at_fdcwd,
        os.fsencode(staging_dir),
        at_fdcwd,
        os.fsencode(output_dir),
        rename_excl,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), output_dir)


def main() -> None:
    args = parse_args()
    fixed_inputs = (
        (args.baseline, EXPECTED_BASELINE_SHA256, "baseline"),
        (args.proposals, EXPECTED_PROPOSALS_SHA256, "proposals"),
        (args.evidence, EXPECTED_EVIDENCE_SHA256, "evidence"),
    )
    for path, expected, label in fixed_inputs:
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"{label} SHA mismatch: {actual}")
    input_identities = {
        "baseline": file_identity(args.baseline),
        "proposals": file_identity(args.proposals),
        "signed_per_view_evidence": file_identity(args.evidence),
    }
    validate_output_layout(
        (args.baseline, args.proposals, args.evidence),
        args.output_dir,
    )

    baseline_payload, baseline_count = read_ply(args.baseline)
    proposal_payload, proposal_count = read_ply(args.proposals)
    if baseline_count != EXPECTED_BASELINE_POINTS:
        raise ValueError("unexpected baseline point count")
    if proposal_count != EXPECTED_PROPOSALS:
        raise ValueError("unexpected proposal point count")

    evidence_rows = load_evidence(args.evidence)
    certified_parts: list[bytes] = []
    deferred_parts: list[bytes] = []
    decisions: list[dict[str, Any]] = []
    for index, evidence in enumerate(evidence_rows):
        counts = validate_evidence_row(evidence, row_index=index)
        agreement = counts["AGREEMENT"]
        conflict = counts["FREE_SPACE_CONFLICT"]
        occluded = counts["OCCLUDED_ABSTAIN"]
        abstain = counts["ABSTAIN"]

        decision = decide_birth(
            agreement=agreement,
            free_space_conflict=conflict,
        )
        start = index * PLY_RECORD.size
        record = proposal_payload[start : start + PLY_RECORD.size]
        if decision == "CERTIFIED":
            certified_parts.append(record)
        else:
            deferred_parts.append(record)
        decisions.append(
            {
                "proposal_index": index,
                "reference_frame_id": int(evidence["reference_frame_id"]),
                "pixel_index": int(evidence["pixel_index"]),
                "evidence": {
                    "agreement": agreement,
                    "free_space_conflict": conflict,
                    "occluded_abstain": occluded,
                    "uninformative_abstain": abstain,
                },
                "signed_consensus": agreement - conflict,
                "decision": decision,
            }
        )

    certified_payload = b"".join(certified_parts)
    deferred_payload = b"".join(deferred_parts)
    certified_count = len(certified_parts)
    deferred_count = len(deferred_parts)
    if (certified_count, deferred_count) != (
        EXPECTED_CERTIFIED,
        EXPECTED_DEFERRED,
    ):
        raise ValueError(
            "unexpected partition: "
            f"certified={certified_count}, deferred={deferred_count}"
        )
    if certified_count + deferred_count != proposal_count:
        raise ValueError("proposal partition is not exhaustive")

    output_dir = args.output_dir.resolve(strict=False)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.tmp-",
            dir=output_dir.parent,
        )
    )
    try:
        candidate_path = staging_dir / "candidate_full.ply"
        certified_path = staging_dir / "added_certified.ply"
        deferred_path = staging_dir / "deferred_only.ply"
        decisions_path = staging_dir / "decisions.jsonl"
        manifest_path = staging_dir / "manifest.json"

        candidate_payload = baseline_payload + certified_payload
        candidate = make_ply(
            baseline_count + certified_count,
            candidate_payload,
            "U2 source-agnostic signed-consensus certified proposals",
        )
        certified = make_ply(
            certified_count,
            certified_payload,
            "U2 proposals certified before product-visible birth",
        )
        deferred = make_ply(
            deferred_count,
            deferred_payload,
            "U2 proposals deferred before product-visible birth",
        )
        decision_bytes = "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in decisions
        ).encode("utf-8")
        candidate_path.write_bytes(candidate)
        certified_path.write_bytes(certified)
        deferred_path.write_bytes(deferred)
        decisions_path.write_bytes(decision_bytes)

        candidate_payload_roundtrip, candidate_count = read_ply(candidate_path)
        if candidate_payload_roundtrip[: len(baseline_payload)] != baseline_payload:
            raise ValueError("candidate does not preserve baseline payload byte-for-byte")
        if candidate_payload_roundtrip[len(baseline_payload) :] != certified_payload:
            raise ValueError("candidate certified suffix mismatch")

        outputs = {
            "candidate_full": file_identity(
                candidate_path,
                reported_path=output_dir / candidate_path.name,
            ),
            "added_certified": file_identity(
                certified_path,
                reported_path=output_dir / certified_path.name,
            ),
            "deferred_only": file_identity(
                deferred_path,
                reported_path=output_dir / deferred_path.name,
            ),
            "decisions": file_identity(
                decisions_path,
                reported_path=output_dir / decisions_path.name,
            ),
        }
        manifest = {
            "schema": "pocketworld_unified_birth_controller_u2_v1",
            "north_star": "RealityScan-class coherent visible surfaces",
            "inputs": input_identities,
            "rule": {
                "source_agnostic": True,
                "decision": (
                    "DEFERRED iff reliable FREE_SPACE_CONFLICT count is strictly "
                    "greater than AGREEMENT count; otherwise CERTIFIED"
                ),
                "occlusion": "ABSTAIN",
                "uninformative": "ABSTAIN",
                "tunable_parameters_added": 0,
                "post_publication_deletion": False,
                "private_source_gate": False,
            },
            "proposal_source_status": {
                "legacy_device_sparse": "byte-exact baseline passthrough for U2-1",
                "detector_free_candidates": "evaluated by the global controller",
                "known_plane_candidates": (
                    "not published: no unified per-view evidence certificate yet"
                ),
            },
            "counts": {
                "baseline": baseline_count,
                "proposals": proposal_count,
                "certified": certified_count,
                "deferred": deferred_count,
                "candidate_full": candidate_count,
            },
            "outputs": outputs,
            "validation": {
                "baseline_payload_byte_exact_prefix": True,
                "certified_suffix_exact_subsequence": True,
                "partition_exhaustive": True,
                "decisions_in_exact_proposal_record_order": True,
                "no_post_publication_deletion": True,
            },
        }
        manifest_path.write_bytes(
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        publish_directory_no_replace(staging_dir, output_dir)
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    print(json.dumps(manifest["counts"], sort_keys=True))
    print(f"candidate_sha256={outputs['candidate_full']['sha256']}")
    print(f"manifest={(output_dir / 'manifest.json').resolve()}")


if __name__ == "__main__":
    main()
