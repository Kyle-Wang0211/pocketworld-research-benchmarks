# -*- coding: utf-8 -*-
"""与 /root/sp_fetch.py 同一调用 (hf_hub_download, 自带 etag/大小校验), 只是 4 线程并行拉 [lo, hi)。"""
import os, sys
import concurrent.futures as cf
from huggingface_hub import hf_hub_download

lo, hi = int(sys.argv[1]), int(sys.argv[2])


def get(i):
    fn = "shard-%06d.tar" % i
    p = hf_hub_download("princeton-vl/SimpleProc", fn, repo_type="dataset", local_dir="/root/sp_raw")
    return fn, os.path.getsize(p)


with cf.ThreadPoolExecutor(4) as ex:
    for fn, sz in ex.map(get, range(lo, hi)):
        print("got", fn, sz, flush=True)
print("DONE", flush=True)
