#!/bin/zsh
ssh -p 45434 -o BatchMode=yes -o ConnectTimeout=25 \
  -o ControlMaster=auto -o ControlPath=~/.ssh/cm/pw-%p -o ControlPersist=20m \
  root@107.209.104.125 "$@" 2>&1 | grep -v -e '^Welcome to vast.ai' -e '^Have fun!' -e '^AI agents: READ'
