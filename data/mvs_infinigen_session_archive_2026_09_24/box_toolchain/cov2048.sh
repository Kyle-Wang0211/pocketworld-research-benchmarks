#!/bin/bash
cd /root && /venv/main/bin/python -u cover2.py C768px1=/root/bins_gate T1768=/root/bins_gate T1_2048=/root/bins_gate > /root/cov2048.out 2>&1
touch /root/COV2048_DONE
