#!/bin/bash
while ps -eo command | awk "/migrate_rest\.sh/ && !/awk/" | grep -q .; do sleep 30; done
echo "[$(date +%H:%M)] 搬运结束, 触发新机 post_migrate" >> /root/migrate_rest.log
ssh -p 45434 -o StrictHostKeyChecking=no root@107.209.104.125 "setsid nohup /root/post_migrate.sh </dev/null >/dev/null 2>&1 &"
