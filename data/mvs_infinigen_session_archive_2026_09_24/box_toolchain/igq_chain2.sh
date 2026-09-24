#!/bin/bash
for i in $(seq 1 400); do [ -f /root/IGQ2_PHASE1 ] && break; sleep 15; done
/root/igq4.sh 1536 1152
/root/igq3.sh 1536 1152
