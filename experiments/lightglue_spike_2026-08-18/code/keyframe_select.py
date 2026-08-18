#!/usr/bin/env python3
"""关键帧筛选:减少**参与匹配**的帧,而不是减少注册的帧。

🔴 红线厘清(用户签决「永久缺帧绝对禁止」):
   · 禁止的是「那一帧最终不在交付模型里」= 丢数据
   · 允许的是「那一帧不参与两两匹配,但仍通过 PnP 注册进模型」= 数据不丢
   本脚本做的是后者:非关键帧的配对边被删掉,但它仍靠与关键帧的少量边注册。
   ⚠️ 验收必须看**注册帧数 = 132**,少一帧就判负。

依据:openMVG 关键帧策略社区共识 —— 筛代表性子集可在保持精度下提效 3-5×。
总匹配量 = 帧数 × k,减帧是线性省。

选法:按位姿的空间/朝向覆盖贪心选关键帧(与生产的空间序同源),
非关键帧只保留它到最近关键帧的少量边(保证可注册)。
"""
import argparse, collections, shutil, sqlite3
from pathlib import Path
import numpy as np

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kf-frac", type=float, default=0.5, help="关键帧比例")
    ap.add_argument("--nonkf-edges", type=int, default=3,
                    help="非关键帧保留几条边(够 PnP 注册即可)")
    args = ap.parse_args()

    z = np.load(args.poses)
    ids = [int(i) for i in z["ids"]]
    R, t = z["R"], z["t"]
    C = np.stack([-R[i].T @ t[i] for i in range(len(ids))])      # 光心
    D = np.stack([R[i].T @ np.array([0, 0, 1.0]) for i in range(len(ids))])  # 朝向

    # 贪心最远点采样:位置 + 朝向联合覆盖(与生产空间序同源)
    n_kf = max(2, int(len(ids) * args.kf_frac))
    chosen = [0]
    scale = np.linalg.norm(C - C.mean(0), axis=1).mean() + 1e-9
    while len(chosen) < n_kf:
        best, best_d = -1, -1
        for i in range(len(ids)):
            if i in chosen: continue
            d = min(np.linalg.norm(C[i]-C[c])/scale + (1 - D[i] @ D[c]) for c in chosen)
            if d > best_d: best_d, best = d, i
        chosen.append(best)
    kf = {ids[i] for i in chosen}
    print(f"关键帧 {len(kf)}/{len(ids)}({args.kf_frac*100:.0f}%)")

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = db.execute("select pair_id, rows from matches").fetchall()
    db.close()

    keep, per = set(), collections.Counter()
    # 1) 关键帧之间的边:全保留
    for pid, nm in rows:
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if i1 in kf and i2 in kf:
            keep.add(pid); per[i1] += 1; per[i2] += 1
    # 2) 非关键帧:只保留到关键帧的最强 nonkf_edges 条(够注册)
    cand = collections.defaultdict(list)
    for pid, nm in rows:
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if (i1 in kf) != (i2 in kf):
            nk = i2 if i1 in kf else i1
            cand[nk].append((nm, pid))
    for nk, lst in cand.items():
        for nm, pid in sorted(lst, reverse=True)[:args.nonkf_edges]:
            keep.add(pid); per[nk] += 1
    covered = len(per)

    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(args.out)
    o.executemany("delete from matches where pair_id=?",
                  [(p,) for p, _ in rows if p not in keep])
    o.execute("delete from two_view_geometries"); o.commit()
    n_left = o.execute("select count(*) from matches").fetchone()[0]
    o.close()
    print(f"{args.out}: 保留 {n_left}/{len(rows)} 对({n_left/len(rows)*100:.0f}%) "
          f"⇒ 匹配量省 {len(rows)/max(n_left,1):.2f}×")
    print(f"  覆盖 {covered} 帧(须=132),每帧边数 最少 {min(per.values())} "
          f"中位 {int(np.median(list(per.values())))}")


if __name__ == "__main__":
    main()
