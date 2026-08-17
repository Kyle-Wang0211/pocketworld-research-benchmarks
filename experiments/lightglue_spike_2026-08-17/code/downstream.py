#!/usr/bin/env python3
"""对任一 DB 跑同一套下游:几何验证 → 增量建图 → 指标。

两臂唯一的差别只能是 matches 表的内容;验证与建图参数逐字相同,
这样测出来的差就是"换匹配器"这一个变量的效应。

注意:这里用 pycolmap 4.0.4 的默认建图参数,不是我们产品核的流式配置。
所以绝对数字不等于生产数字,**只有两臂之差**是有意义的。
"""
import argparse, shutil, sqlite3, sys, time
from pathlib import Path

import pycolmap as pc

MAX_IMAGE_ID = 2147483647


def write_pairs(db_path, pairs_txt):
    db = sqlite3.connect(db_path)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    n = 0
    with open(pairs_txt, "w") as f:
        for (pid,) in db.execute("select pair_id from matches where rows>0"):
            i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
            if i1 in names and i2 in names:
                f.write(f"{names[i1]} {names[i2]}\n")
                n += 1
    db.close()
    return n


def stats(db_path, label):
    db = sqlite3.connect(db_path)
    q = lambda s: db.execute(s).fetchone()
    npair, avgm = q("select count(*), coalesce(avg(rows),0) from matches where rows>0")
    ntvg, avgi = q("select count(*), coalesce(avg(rows),0) from two_view_geometries where rows>0")
    db.close()
    print(f"[{label}] 配对 {npair}  平均匹配 {avgm:.1f}  |  验证通过 {ntvg}  平均内点 {avgi:.1f}"
          f"  |  验证存活率 {ntvg/max(npair,1)*100:.1f}%")
    return dict(pairs=npair, matches=avgm, tvg=ntvg, inliers=avgi)


def recon_metrics(rec, label):
    import numpy as np
    tl = [len(p.track.elements) for p in rec.points3D.values()]
    tl = np.array(tl) if tl else np.array([0])
    print(f"[{label}] 注册帧 {rec.num_reg_images()}/{rec.num_images()}"
          f"  点 {rec.num_points3D()}"
          f"  观测 {int(tl.sum())}"
          f"  轨迹长度 均值 {tl.mean():.2f} 中位 {int(np.median(tl))}"
          f"  ≥3 观测占比 {(tl>=3).mean()*100:.1f}%"
          f"  重投影 {rec.compute_mean_reprojection_error():.4f}px")
    return dict(reg=rec.num_reg_images(), points=rec.num_points3D(),
                obs=int(tl.sum()), track_mean=float(tl.mean()),
                track_ge3=float((tl >= 3).mean()),
                reproj=float(rec.compute_mean_reprojection_error()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--work", required=True, help="工作目录(会复制 DB 进去,不动原件)")
    args = ap.parse_args()

    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    db = work / "work.db"
    shutil.copy(args.db, db)
    for suf in ("-wal", "-shm"):
        Path(str(db) + suf).unlink(missing_ok=True)

    # 清空 TVG,保证两臂都由同一套验证器从零产生
    c = sqlite3.connect(db); c.execute("delete from two_view_geometries"); c.commit(); c.close()

    pairs_txt = work / "pairs.txt"
    n = write_pairs(db, pairs_txt)
    print(f"[{args.label}] 待验证配对 {n}", flush=True)

    t0 = time.perf_counter()
    pc.verify_matches(db, pairs_txt, pc.TwoViewGeometryOptions())
    print(f"[{args.label}] 几何验证 {time.perf_counter()-t0:.1f}s", flush=True)
    s = stats(db, args.label)

    out = work / "sparse"; out.mkdir(exist_ok=True)
    imgdir = work / "noimg"; imgdir.mkdir(exist_ok=True)
    opts = pc.IncrementalPipelineOptions()
    opts.extract_colors = False
    t0 = time.perf_counter()
    recs = pc.incremental_mapping(db, imgdir, out, opts)
    print(f"[{args.label}] 建图 {time.perf_counter()-t0:.1f}s,子模型 {len(recs)}", flush=True)

    if not recs:
        print(f"[{args.label}] 🔴 没有产出重建"); return
    best = max(recs.values(), key=lambda r: r.num_reg_images())
    m = recon_metrics(best, args.label)
    import json
    (work / "metrics.json").write_text(json.dumps({**s, **m}, indent=2))


if __name__ == "__main__":
    main()
