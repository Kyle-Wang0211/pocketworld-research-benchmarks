#!/bin/bash
# 下载我们 28 个 TartanAir 环境 x 2 难度的官方分割 (seg_lcam_front), 共 56 个 zip / 6.9 GB。
# zip 内自带 pose_lcam_front.txt, 用于把【输出帧 j <-> 源帧 i】用相机中心精确对回去。
set -u
/venv/main/bin/python - <<PY
import os
from huggingface_hub import hf_hub_download
envs=sorted({d[3:].rsplit("_",2)[0] for d in os.listdir("/root/monotrain") if d.startswith("ta_")})
want=[f"{e}/Data_{d}/seg_lcam_front.zip" for e in envs for d in ("easy","hard")]
print("要下 %d 个" % len(want), flush=True)
ok=0; tot=0
for i,f in enumerate(want):
    try:
        p=hf_hub_download("theairlabcmu/tartanair2", f, repo_type="dataset", local_dir="/root/ta_seg_probe")
        sz=os.path.getsize(p); tot+=sz; ok+=1
        print("  [%2d/%d] %-52s %.3f GB" % (i+1,len(want),f,sz/1e9), flush=True)
    except Exception as e:
        print("  [%2d/%d] 🔴 %s -> %s" % (i+1,len(want),f,str(e)[:80]), flush=True)
print("完成 %d/%d, 合计 %.2f GB" % (ok,len(want),tot/1e9))
PY
touch /root/DLSEG_DONE
