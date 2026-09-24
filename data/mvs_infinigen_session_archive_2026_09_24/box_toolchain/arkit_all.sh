#!/bin/bash
/root/arkit_stream.sh Training /root/arkit_train_ids.txt 8
/root/arkit_stream.sh Validation /root/arkit_val_ids.txt 8
echo "[ALL DONE $(date +%m-%d\ %H:%M)] $(ls -d /root/arkit_blend/ak_* | wc -l) scans"
