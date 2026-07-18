#!/usr/bin/env python3
"""make_meta2.py <solved_poses.csv> <dst_meta.json> — device-meta-schema poses from a replay."""
import csv, json, os, sys

src, dst = sys.argv[1], sys.argv[2]
poses = []
with open(src) as f:
    for row in csv.DictReader(f):
        poses.append({
            "frame_id": int(row["frame_id"]),
            "registered": bool(int(row["registered"])),
            "quat_wxyz": [float(row[k]) for k in ("qw", "qx", "qy", "qz")],
            "t": [float(row[k]) for k in ("tx", "ty", "tz")],
        })
os.makedirs(os.path.dirname(dst), exist_ok=True)
if os.path.islink(dst):
    os.remove(dst)
json.dump({"schema": "replay_solved_poses_v1", "refined": True, "source": src,
           "n_points": None, "poses": poses}, open(dst, "w"))
print(f"wrote {dst}: {len(poses)} poses, registered={sum(p['registered'] for p in poses)}")
