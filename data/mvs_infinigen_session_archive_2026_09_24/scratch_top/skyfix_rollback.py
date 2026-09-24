#!/usr/bin/env python3
"""skyfix 回滚 (09-23 用户决定: 本轮训练用 TartanAir 原始数据)。
/root/skyfix_backup.tsv 每行 = path \t 旧末行 \t 新末行 (skyfix.py:19「改写前把所有旧值存进 backup, 可完整回滚」)。
只在「当前末行 == 备份里的新末行」时才写回旧末行; 不匹配的一律不动并报告。--dry 只核对不写。"""
import sys, os
from concurrent.futures import ThreadPoolExecutor
DRY = "--dry" in sys.argv
rows = [l.rstrip("\n").split("\t") for l in open("/root/skyfix_backup.tsv")]
def one(r):
    path, old, new = r
    try: raw = open(path, "rb").read().decode()
    except Exception as e: return ("missing", path)
    body = raw.rstrip("\n"); tail = raw[len(body):]           # 保住原文件结尾的换行
    head, sep, last = body.rpartition("\n")
    if last.strip() == old.strip(): return ("already_old", path)
    if last.strip() != new.strip(): return ("mismatch", path + " | now=" + last.strip() + " | new=" + new)
    if not DRY:
        tmp = path + ".rb_tmp"
        open(tmp, "wb").write((head + sep + old + tail).encode()); os.replace(tmp, path)
    return ("restored", path)
with ThreadPoolExecutor(32) as ex: res = list(ex.map(one, rows))
from collections import Counter
c = Counter(k for k, _ in res); print(("DRY-RUN " if DRY else "") + str(dict(c)), "total", len(rows))
for k, p in res:
    if k in ("mismatch", "missing"): print(" ", k, p); 
