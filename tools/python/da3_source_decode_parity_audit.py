#!/usr/bin/env python3
"""Compare official PIL source decode with Dart package:image source decode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-image", type=Path, required=True)
    parser.add_argument("--dart-decoded-png", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_source_decode_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_source_decode_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official = np.asarray(Image.open(args.source_image).convert("RGB"), dtype=np.int16)
    dart = np.asarray(Image.open(args.dart_decoded_png).convert("RGB"), dtype=np.int16)
    shape_match = official.shape == dart.shape
    if shape_match:
        diff = dart - official
        abs_diff = np.abs(diff)
        unique_values, counts = np.unique(diff, return_counts=True)
        histogram = [
            {"diff": int(value), "count": int(count)}
            for value, count in zip(unique_values, counts)
            if -12 <= int(value) <= 12
        ]
        channel_stats = []
        for index, name in enumerate(("R", "G", "B")):
            channel = diff[..., index]
            channel_abs = np.abs(channel)
            channel_stats.append(
                {
                    "channel": name,
                    "min": int(channel.min()),
                    "max": int(channel.max()),
                    "mean_abs": float(channel_abs.mean()),
                    "nonzero": int((channel != 0).sum()),
                }
            )
        max_abs = int(abs_diff.max())
        mean_abs = float(abs_diff.mean())
        nonzero = int((diff != 0).sum())
        total = int(diff.size)
    else:
        histogram = []
        channel_stats = []
        max_abs = None
        mean_abs = None
        nonzero = None
        total = None

    status = "pass_exact_decode_parity" if shape_match and max_abs == 0 else "warning_source_decode_not_byte_exact"
    return {
        "schema_version": "aether_official_da3_source_decode_parity_audit_v1",
        "date": args.date,
        "source_image": str(args.source_image),
        "dart_decoded_png": str(args.dart_decoded_png),
        "decision": {
            "status": status,
            "shape_match": shape_match,
            "byte_exact": shape_match and max_abs == 0,
            "max_abs_uint8": max_abs,
            "mean_abs_uint8": mean_abs,
            "nonzero_values": nonzero,
            "total_values": total,
            "interpretation": (
                "Official DA3 loads source images through PIL; Dart package:image JPEG decode is not byte-exact. "
                "Preprocess pixel parity cannot be closed by resize math alone until source decode parity is addressed."
            )
            if status != "pass_exact_decode_parity"
            else "Official PIL decode and Dart decode are byte-exact for this source.",
        },
        "histogram": histogram,
        "channel_stats": channel_stats,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 source decode parity audit",
        "",
        f"- status: `{decision['status']}`",
        f"- shape match: `{decision['shape_match']}`",
        f"- byte exact: `{decision['byte_exact']}`",
        f"- max abs uint8: `{decision['max_abs_uint8']}`",
        f"- mean abs uint8: `{decision['mean_abs_uint8']}`",
        f"- nonzero values: `{decision['nonzero_values']}` / `{decision['total_values']}`",
        "",
        "## Interpretation",
        "",
        decision["interpretation"],
        "",
        "## Channels",
        "",
        "| channel | min | max | mean abs | nonzero |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report["channel_stats"]:
        lines.append(
            f"| `{row['channel']}` | {row['min']} | {row['max']} | "
            f"{row['mean_abs']:.6f} | {row['nonzero']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
