#!/bin/bash
set -u
cd /root
/venv/main/bin/python -u skyfix.py --stage rewrite --workers 16
touch /root/SKYFIX_DONE
