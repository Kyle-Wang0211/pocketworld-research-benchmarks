#!/bin/bash
# 台湾机上生成一次性迁移密钥 (只用于把数据直传到印度新机, 传完即删)
set -e
rm -f /root/.ssh/mig_tmp /root/.ssh/mig_tmp.pub
ssh-keygen -q -t ed25519 -N "" -C "mig_tmp_$(date +%Y%m%d)" -f /root/.ssh/mig_tmp
cat /root/.ssh/mig_tmp.pub
