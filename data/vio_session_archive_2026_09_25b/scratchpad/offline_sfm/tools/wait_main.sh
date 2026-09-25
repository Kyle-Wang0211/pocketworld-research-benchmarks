#!/bin/bash
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
until grep -qE "主批完成|停止于|STOP" $O/batch_main.log 2>/dev/null; do sleep 5; done
