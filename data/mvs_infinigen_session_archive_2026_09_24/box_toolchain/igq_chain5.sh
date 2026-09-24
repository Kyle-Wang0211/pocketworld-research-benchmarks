#!/bin/bash
for i in $(seq 1 900); do [ -f /root/IGQ6_DONE ] && break; sleep 20; done
/root/igq7.sh
