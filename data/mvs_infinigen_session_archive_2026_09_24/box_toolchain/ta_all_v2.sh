#!/bin/bash
# TartanAir v2: 逐环境 下载(tartanair 工具包, HF 源) -> dvmvs 关键帧规则转换 -> 删原始
LOG=/root/ta_all_v2.log; exec >> $LOG 2>&1
PY=/venv/main/bin/python; RAW=/root/ta_raw; OUT=/root/ta2/blendfmt_v2
echo "=== [$(date +%m-%d\ %H:%M)] ta_all_v2 起 ==="
while read -r ENV; do
  [ -z "$ENV" ] && continue
  echo "--- [$(date +%H:%M)] $ENV 下载 ---"
  $PY - <<PYEOF 2>&1 | grep -vE "Unzipping|Removed|Downloading|%\|" | tail -3
import tartanair as ta
ta.init("$RAW")
for diff in ("easy", "hard"):
    try:
        ta.download(env=["$ENV"], difficulty=[diff], modality=["image","depth"], camera_name=["lcam_front"], unzip=True, delete_zip=True, num_workers=8, data_source="huggingface")
    except Exception as e:
        print("[dl warn] $ENV", diff, str(e)[:120])
PYEOF
  echo "--- [$(date +%H:%M)] $ENV 转换 (keyframe 0.1) ---"
  (cd /root/ta2 && $PY tartanair_to_blend.py --root $RAW --out $OUT --envs $ENV --keyframe_dist 0.1 2>&1 | grep -E "SKIP|帧|DONE")
  rm -rf $RAW/$ENV
  echo "[$ENV done $(date +%H:%M)] 累计 scan $(ls -d $OUT/*/ | wc -l)  盘剩 $(df -h / | tail -1 | awk "{print \$4}")"
done < /root/ta_envs.txt
echo "=== [$(date +%H:%M)] ta_all_v2 完成 ==="
