#!/usr/bin/env python3
"""Clone a capture DB and bind every image to its exact captured-frame K."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--sidecar-dir", type=Path, required=True)
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_db.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{args.output_db}{suffix}").unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{args.source_db}?mode=ro", uri=True)
    cloned = sqlite3.connect(args.output_db)
    source.backup(cloned)
    cloned.close()
    source.close()

    ledger = {}
    with args.ledger.open() as stream:
        for line in stream:
            row = json.loads(line)
            ledger[int(row["frameId"])] = Path(row["jpegPath"]).stem

    connection = sqlite3.connect(args.output_db)
    images = connection.execute(
        "SELECT image_id, name FROM images ORDER BY image_id"
    ).fetchall()
    if len(images) != len(ledger):
        raise RuntimeError(f"images={len(images)} ledger={len(ledger)}")

    rows = []
    with connection:
        next_camera_id = connection.execute(
            "SELECT COALESCE(MAX(camera_id), 0) + 1 FROM cameras"
        ).fetchone()[0]
        for image_id, image_name in images:
            frame_id = int(Path(image_name).stem.split("_")[-1])
            sidecar = args.sidecar_dir / f"{ledger[frame_id]}.json"
            payload = json.loads(sidecar.read_text())
            fx, fy, cx, cy = map(float, payload["intrinsics_fxfycxcy"])
            width = int(payload["image_w"])
            height = int(payload["image_h"])
            if abs(fx - fy) > 0.05:
                raise RuntimeError(f"non-square pixels in {sidecar}: {fx}, {fy}")
            camera_id = next_camera_id
            next_camera_id += 1
            params = struct.pack("<ddd", 0.5 * (fx + fy), cx, cy)
            connection.execute(
                "INSERT INTO cameras(camera_id, model, width, height, params, "
                "prior_focal_length) VALUES (?, 0, ?, ?, ?, 1)",
                (camera_id, width, height, params),
            )
            connection.execute(
                "UPDATE images SET camera_id=? WHERE image_id=?",
                (camera_id, image_id),
            )
            rows.append(
                {
                    "frame_id": frame_id,
                    "image_id": image_id,
                    "camera_id": camera_id,
                    "sidecar": sidecar.name,
                    "fx": fx,
                    "fy": fy,
                    "cx": cx,
                    "cy": cy,
                    "width": width,
                    "height": height,
                }
            )
    connection.close()

    manifest = {
        "schema": "pocketworld_per_frame_intrinsics_ab_v1",
        "source_db": str(args.source_db.resolve()),
        "source_db_sha256": sha256(args.source_db),
        "output_db": str(args.output_db.resolve()),
        "output_db_sha256": sha256(args.output_db),
        "ledger": str(args.ledger.resolve()),
        "ledger_sha256": sha256(args.ledger),
        "num_images": len(rows),
        "cameras": rows,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({
        "num_images": len(rows),
        "fx_min": min(row["fx"] for row in rows),
        "fx_max": max(row["fx"] for row in rows),
        "cx_min": min(row["cx"] for row in rows),
        "cx_max": max(row["cx"] for row in rows),
        "output_sha256": manifest["output_db_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
