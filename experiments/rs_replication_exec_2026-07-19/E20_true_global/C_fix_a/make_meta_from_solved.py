#!/usr/bin/env python3
"""Build sfm_sparse_meta.json (device meta schema) from a replay's solved_poses.csv
so the TRAILS/E3 stack can consume a replay cloud with ITS OWN refined poses."""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, "runs", "cap50_debt_r1", "solved_poses.csv")
poses = []
with open(src) as f:
    for row in csv.DictReader(f):
        poses.append({
            "frame_id": int(row["frame_id"]),
            "registered": bool(int(row["registered"])),
            "quat_wxyz": [float(row[k]) for k in ("qw", "qx", "qy", "qz")],
            "t": [float(row[k]) for k in ("tx", "ty", "tz")],
        })
out = {"schema": "replay_solved_poses_v1", "refined": True,
       "source": src, "n_points": None, "poses": poses}
dst = os.path.join(HERE, "cap50_fixA_inputs", "sfm_sparse_meta.json")
os.makedirs(os.path.dirname(dst), exist_ok=True)
json.dump(out, open(dst, "w"))
print(f"wrote {dst}: {len(poses)} poses, registered={sum(p['registered'] for p in poses)}")
