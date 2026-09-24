#!/bin/bash
ssh -p 45434 -o BatchMode=yes -o ConnectTimeout=20 -o ControlMaster=auto -o ControlPath=~/.ssh/cm/ig-%r@%h:%p -o ControlPersist=600 root@107.209.104.125 "$@"
