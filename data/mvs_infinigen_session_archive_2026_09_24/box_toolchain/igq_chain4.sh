#!/bin/bash
for i in $(seq 1 800); do [ -f /root/IGQ5_DONE ] && break; sleep 20; done
/root/igq6.sh
