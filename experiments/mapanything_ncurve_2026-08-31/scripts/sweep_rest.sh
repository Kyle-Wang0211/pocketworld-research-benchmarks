#!/bin/zsh
cd "$(dirname "$0")"; source .venv/bin/activate
python conf_sweep.py 30 1 mv_p30 2>&1 | grep -E "^  mv|Traceback"
python conf_sweep.py 60 1 mv_p60 2>&1 | grep -E "^  mv|Traceback"
echo DONE
