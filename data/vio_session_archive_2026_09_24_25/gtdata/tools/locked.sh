#!/bin/bash
# locked.sh <cmd...> : run under the shared xrslam replay lock (same protocol as S3/S4)
L=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/.xrslam_run.lock
until mkdir "$L" 2>/dev/null; do sleep 5; done
echo "GT $$ $(date +%T) $*" > "$L/owner"
trap 'rm -f "$L/owner"; rmdir "$L"' EXIT
"$@"
