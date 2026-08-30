#!/bin/bash
# Pulls every run off the device and verifies it against the run's own
# SHA256SUMS. A capture that exists only on the phone is one purge away from
# being gone -- which is exactly how a hand-shot 30 s recording, 1769 frames,
# was lost. Nothing here deletes anything on the device.
set -euo pipefail

DEVICE="${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}"
BUNDLE="com.kyle.viobench"
DEST="${1:-$HOME/Developer/viobench-recordings}"

runs=$(xcrun devicectl device info files --device "$DEVICE" \
    --domain-type appDataContainer --domain-identifier "$BUNDLE" --username mobile 2>&1 \
    | grep -oE "run-[a-f0-9-]{36}" | sort -u)

[ -z "$runs" ] && { echo "设备上没有 run"; exit 0; }

for run in $runs; do
    out="$DEST/$run"
    if [ -f "$out/.backup_complete" ]; then
        echo "跳过 $run(已备份)"
        continue
    fi
    echo "拉取 $run ..."
    mkdir -p "$out"
    # copy from on the directory brings the whole tree, frames included.
    xcrun devicectl device copy from --device "$DEVICE" \
        --domain-type appDataContainer --domain-identifier "$BUNDLE" --user mobile \
        --source "Documents/VIOBenchRuns/$run" --destination "$out" >/dev/null

    inner="$out/$run"
    [ -d "$inner" ] && { mv "$inner"/* "$out"/ 2>/dev/null || true; rmdir "$inner" 2>/dev/null || true; }

    if [ -f "$out/SHA256SUMS" ]; then
        # SHA256SUMS covers the run's own files, so verification runs from inside it.
        if (cd "$out" && shasum -a 256 -c SHA256SUMS --quiet 2>/dev/null); then
            echo "  ✓ 校验通过($(ls "$out/frames" 2>/dev/null | wc -l | tr -d ' ') 帧)"
            touch "$out/.backup_complete"
        else
            echo "  ✗ 校验失败,保留但不标记完成:$out"
        fi
    else
        echo "  ⚠ 无 SHA256SUMS,无法校验(run 未正常收尾),已保留原样"
    fi
done
echo "备份目录:$DEST"
