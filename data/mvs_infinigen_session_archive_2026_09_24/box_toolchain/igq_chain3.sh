#!/bin/bash
for i in $(seq 1 400); do [ -f /root/IGQ3_DONE ] && break; sleep 20; done
/root/igq5.sh 768 576
