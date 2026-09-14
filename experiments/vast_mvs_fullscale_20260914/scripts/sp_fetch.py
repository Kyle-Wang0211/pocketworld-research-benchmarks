import sys, os
from huggingface_hub import hf_hub_download
lo, hi = int(sys.argv[1]), int(sys.argv[2])
for i in range(lo, hi):
    fn = "shard-%06d.tar" % i
    dst = "/root/sp_raw/" + fn
    if os.path.exists(dst):
        print("skip", fn, flush=True); continue
    hf_hub_download("princeton-vl/SimpleProc", fn, repo_type="dataset", local_dir="/root/sp_raw")
    print("got", fn, os.path.getsize(dst), flush=True)
print("DONE")
