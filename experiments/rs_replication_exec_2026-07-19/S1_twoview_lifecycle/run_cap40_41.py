#!/usr/bin/env python3.11
"""E2-D S1 backfill: run the SAME unified 2-view lifecycle rule (build_candidate.py,
untouched) on cap40 (full pull) and cap41 (db pull) to complete the 4-scene set.
Injects cap configs via import — does NOT modify the shared build_candidate.py.
cap40: registered 84/89; cap41: registered 95/102 (closure gap reported as-is).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate as bc

bc.CAPS["cap40"] = {
    "dir": f"{bc.ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17",
    "chair_roi": None,
}
bc.CAPS["cap41"] = {
    "dir": f"{bc.ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17",
    "chair_roi": None,
}

if __name__ == "__main__":
    caps = sys.argv[1:] or ["cap40", "cap41"]
    all_path = os.path.join(bc.OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = bc.run_cap(cap, bc.CAPS[cap])
    json.dump(allstats, open(all_path, "w"), indent=2)
    bc.log("ALL DONE")
