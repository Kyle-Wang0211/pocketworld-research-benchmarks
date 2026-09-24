#!/bin/bash
# retrying ssh wrapper
for i in 1 2 3 4 5; do
  out=$(ssh -p 45434 -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 root@107.209.104.125 "$@" 2>&1)
  rc=$?
  if ! echo "$out" | grep -q 'kex_exchange_identification\|Connection reset by peer'; then
    echo "$out"; exit $rc
  fi
  sleep 4
done
echo "$out"; exit $rc
