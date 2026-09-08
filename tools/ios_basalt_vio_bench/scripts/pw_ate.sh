#!/bin/bash
# pw_ate.sh <run-dir> —— 回放轨迹 vs 共享录制的 ARKit 轨迹(Sim3/SE3 ATE + 尺度偏差);系统 numpy 坏,走 uv
R=~/Developer/viobench-recordings; cd "$R" && uv run --quiet --with numpy python ate.py "$1/poses.tum" "$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum" 2>&1 | tail -3 | tr '\n' ' '; echo
