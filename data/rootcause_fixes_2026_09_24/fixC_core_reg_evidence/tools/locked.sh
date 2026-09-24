#!/bin/bash
# locked.sh <cmd...> — shared core-run lock + disk check around ONE core run.
LOCK=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/.core_run.lock
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}')
if [ "$avail_kb" -lt $((2*1024*1024)) ]; then echo "SKIP_DISK avail=$(df -h ~ | tail -1 | awk '{print $4}') $*"; exit 91; fi
waited=0
until mkdir "$LOCK" 2>/dev/null; do sleep 5; waited=$((waited+5)); done
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
[ $waited -gt 0 ] && echo "  (waited ${waited}s for core lock)"
"$@"
