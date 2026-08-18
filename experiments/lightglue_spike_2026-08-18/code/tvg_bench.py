#!/usr/bin/env python3
"""TVG 几何验证的耗时与存活率:LightGlue 匹配 vs 生产暴力匹配。

为什么要单独量:生产每帧 1.76s 的匹配预算里,纯 GEMM 只占 0.61s(12对×50.6ms),
其余 ~1.15s 是 TVG 验证等下游。LightGlue 匹配质量更高(内点率、匹配数),
**验证的成本可能变化**——如果变便宜,就等于给每帧预算腾地方。

⚠️ 必须串行单跑。之前从并行建图的日志里抓的耗时(57.5s vs 3.7s)绝大部分是
   42 核被抢的等待,不是验证本身 —— 那组数互相不可比。
"""
import argparse, shutil, sqlite3, sys, time
from pathlib import Path
import pycolmap as pc

MAX_IMAGE_ID = 2147483647


def bench(db_path, tag, work):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    db = work / "w.db"
    shutil.copy(db_path, db)
    for suf in ("-wal", "-shm"):
        Path(str(db) + suf).unlink(missing_ok=True)
    c = sqlite3.connect(db); c.execute("delete from two_view_geometries"); c.commit()
    npair, avgm = c.execute(
        "select count(*), coalesce(avg(rows),0) from matches where rows>0").fetchone()
    names = dict(c.execute("select image_id,name from images"))
    ptxt = work / "pairs.txt"
    with open(ptxt, "w") as f:
        for (pid,) in c.execute("select pair_id from matches where rows>0"):
            i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
            if i1 in names and i2 in names:
                f.write(f"{names[i1]} {names[i2]}\n")
    c.close()

    t0 = time.perf_counter()
    pc.verify_matches(db, ptxt, pc.TwoViewGeometryOptions())
    dt = time.perf_counter() - t0

    c = sqlite3.connect(db)
    ntvg, avgi = c.execute(
        "select count(*), coalesce(avg(rows),0) from two_view_geometries where rows>0").fetchone()
    c.close()
    print(f"{tag:<16} 配对 {npair:>5} 匹配/对 {avgm:>7.1f} → 内点 {avgi:>7.1f} "
          f"(内点率 {avgi/max(avgm,1)*100:>5.1f}%) 存活 {ntvg/max(npair,1)*100:>5.1f}% "
          f"验证 {dt:>6.2f}s ({dt/max(npair,1)*1000:>5.1f} ms/对)", flush=True)
    return dt, npair


if __name__ == "__main__":
    for tag, db in [("基线(暴力)", "b28_src.db"), ("臂A SIFT+LG", "cu_A.db"),
                    ("ALIKED@4096", "cu_K4096.db"), ("ALIKED@6144", "cu_K6144.db"),
                    ("ALIKED@16384", "cu_P16k.db")]:
        if Path(db).exists():
            bench(db, tag, f"/tmp/tvg_{tag.replace('(','').replace(')','').replace('@','').replace(' ','_')}")
