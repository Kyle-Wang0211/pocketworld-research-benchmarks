#!/usr/bin/env python3
"""流式调度模拟:前缀共视 top-10 + 冻结(M 步不变)+ 尾部重融名单。

共视分数 S 复用 _artifacts/lightglue_spike/mvs_channels.py 的向量化 view_scores
(与官方 colmap_input.py calc_score 同一口径 THETA0=5/SIGMA1=1/SIGMA2=10)。

关键校验:t=132 时每个 ref 的 top-10(有序)必须与官方 pair.txt 完全一致,
否则 S 不能当 pair 通道的替身,直接报错退出。

模拟定义(报告里逐字引用):
  - 拍摄顺序 = 帧名序号 frame_000000 .. frame_000131(拍摄步 t=1..132)。
  - L_i(t) = 对最终 S 的第 i 行做一次全行降序排序(np.argsort[::-1],与
    colmap_input.py:424 同一份代码),再筛掉未拍帧与自身,取前 10。
  - 冻结:L_i 连续 M=10 个拍摄步不变(10 次"来了新帧但列表没变"的转移)
    → 在该步用 L_i 融合,记下当时列表。
  - 拍完:凡冻结列表 ≠ 最终列表(有序比较)的 ref 进重融名单;
    从未冻结的 ref 在尾部做首次融合。
"""
import json
import sys

import numpy as np

SPIKE = "/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike"
sys.path.insert(0, SPIKE)

EXP = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
OUT = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/streaming_fuse_md5_20260818"
SPARSE = f"{EXP}/in_P16k/sparse"
PAIR = f"{EXP}/mvs_P16k/pair.txt"
M = 10
TOP = 10


def images_bin_order(path):
    """images.bin 的**文件顺序**就是 colmap_input.py 的视图下标 —— 逐字节自己解。"""
    import struct
    names = []
    with open(path, "rb") as f:
        num = struct.unpack("<Q", f.read(8))[0]
        for _ in range(num):
            f.read(64)  # image_id + qvec4 + tvec3 + camera_id (idddddddi)
            nm = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                nm += c
            names.append(nm.decode())
            n2d = struct.unpack("<Q", f.read(8))[0]
            f.read(24 * n2d)
    return names


def view_scores_official(rec, order):
    """向量化共视分数,**官方 calc_score 语义**。

    结构抄 mvs_channels.view_scores(把观测展开成 (i,j) 对一次算完),但改掉一处
    与官方不一致的口径:当一个 3D 点在同一张图上有多个 2D 观测(track 合并,
    ALIKED@16k 下常见)时——
      · mvs_channels: 权重乘 occ_i × occ_j(两边观测数的积)
      · 官方 colmap_input.calc_score: 对唯一共视点求和,乘 occ_{ind1}
        (ind1 = 视图下标**较小**的那张图在自己 point3d_ids 里的出现次数,
        因为 queue 只按 i<j 算一次再对称赋值)
    实测 pair(0,2):官方 3696.4032 = occ_i 口径;occ_i×occ_j 口径 = 3976.4588,
    偏 3–15%,把 58/132 个 ref 的 top-10 次序都排错了。
    """
    ids = [rec.find_image_with_name(nm).image_id for nm in order]
    pos = {i: k for k, i in enumerate(ids)}
    n = len(ids)
    C = np.zeros((n, 3))
    for i in ids:
        C[pos[i]] = np.array(rec.images[i].cam_from_world().inverse().translation)

    ii, jj, mm, XX = [], [], [], []
    for _pid, p3 in rec.points3D.items():
        occ = {}
        for e in p3.track.elements:
            if e.image_id in pos:
                k = pos[e.image_id]
                occ[k] = occ.get(k, 0) + 1
        if len(occ) < 2:
            continue
        seen = sorted(occ)                      # 唯一视图下标,升序 ⇒ a<b
        x = p3.xyz
        for a_ in range(len(seen)):
            for b_ in range(a_ + 1, len(seen)):
                ii.append(seen[a_]); jj.append(seen[b_])
                mm.append(occ[seen[a_]])        # 乘 occ_{较小下标} —— 官方口径
                XX.append(x)
    ii = np.array(ii); jj = np.array(jj); mm = np.array(mm, dtype=np.float64)
    XX = np.array(XX)

    v1 = C[ii] - XX
    v2 = C[jj] - XX
    cos = (v1 * v2).sum(1) / (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1))
    th = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    sg = np.where(th <= THETA0, SIGMA1, SIGMA2)
    w = np.exp(-((th - THETA0) ** 2) / (2 * sg ** 2)) * mm

    S = np.zeros((n, n))
    np.add.at(S, (ii, jj), w)
    S = S + S.T                                  # 官方 score[j,i]=score[i,j]
    return S


THETA0, SIGMA1, SIGMA2 = 5.0, 1.0, 10.0          # colmap_input.py 默认值


def read_pair(path):
    out = []
    with open(path) as f:
        n = int(f.readline())
        for _ in range(n):
            ref = int(f.readline())
            toks = f.readline().split()
            out.append((ref, [int(x) for x in toks[1::2]]))
    return out


def main():
    names = images_bin_order(f"{SPARSE}/images.bin")
    n = len(names)
    print(f"views {n},images.bin 顺序前 5:{names[:5]}")

    import pycolmap as pc
    rec = pc.Reconstruction(SPARSE)
    S = view_scores_official(rec, names)

    # colmap_input.py:424 的同一份排序代码,整行一次,前缀只做筛选
    full_rank = [np.argsort(S[i])[::-1] for i in range(n)]

    pair = read_pair(PAIR)
    assert [r for r, _ in pair] == list(range(n))

    # ---- 校验:最终 top-10(有序)必须逐 ref 与 pair.txt 一致 ----
    mism = []
    for i in range(n):
        mine = [int(k) for k in full_rank[i] if k != i][:TOP]
        if mine != pair[i][1]:
            mism.append((i, mine, pair[i][1]))
    if mism:
        print(f"🔴 最终 top-10 与 pair.txt 不一致的 ref:{len(mism)} 个")
        for i, a, b in mism[:5]:
            print(f"  ref {i}\n    mine {a}\n    pair {b}")
        sys.exit(1)
    print(f"✅ 最终 top-10(有序)与官方 pair.txt 132/132 逐 ref 一致")

    # ---- 拍摄顺序:帧名序号 ----
    frame_no = [int(nm.split("_")[1].split(".")[0]) for nm in names]
    assert sorted(frame_no) == list(range(n)), "帧号不连续"
    view_of_step = [None] * n           # 拍摄步 t(1-based)拍的是哪个视图下标
    for v, fn in enumerate(frame_no):
        view_of_step[fn] = v

    # ---- 前缀模拟 ----
    captured = np.zeros(n, bool)
    cur = [None] * n                    # 当前列表
    streak = [0] * n                    # 连续不变的转移数
    frozen_at = [None] * n              # 冻结步
    frozen_list = [None] * n
    for t in range(1, n + 1):
        captured[view_of_step[t - 1]] = True
        for i in range(n):
            if not captured[i] or frozen_at[i] is not None:
                continue
            li = [int(k) for k in full_rank[i] if captured[k] and k != i][:TOP]
            if li == cur[i]:
                streak[i] += 1
            else:
                streak[i] = 0
                cur[i] = li
            if streak[i] >= M and len(li) == TOP:
                frozen_at[i] = t
                frozen_list[i] = li

    final = {i: pair[i][1] for i in range(n)}
    frozen = [i for i in range(n) if frozen_at[i] is not None]
    never = [i for i in range(n) if frozen_at[i] is None]
    refuse = [i for i in frozen if frozen_list[i] != final[i]]
    keep = [i for i in frozen if frozen_list[i] == final[i]]

    print(f"\n拍摄期冻结并融合:{len(frozen)}/{n}")
    print(f"  其中冻结列表==最终列表(免重融):{len(keep)}")
    print(f"  其中冻结列表!=最终列表(重融):{len(refuse)}  {refuse}")
    print(f"从未冻结(尾部首融):{len(never)}  {never}")
    tail = len(refuse) + len(never)
    print(f"尾部工作量:{tail} 帧 × 209ms = {tail*209/1000:.1f}s")
    if frozen:
        fz = [frozen_at[i] for i in frozen]
        print(f"冻结步分布:min {min(fz)} / 中位 {int(np.median(fz))} / max {max(fz)}")

    json.dump({
        "M": M, "top": TOP, "n": n,
        "names": names,
        "frozen_at": frozen_at,
        "frozen_list": frozen_list,
        "final_list": [final[i] for i in range(n)],
        "refuse": refuse, "never_frozen": never, "keep": keep,
        "tail_frames": tail, "tail_ms": tail * 209,
    }, open(f"{OUT}/schedule.json", "w"))
    print(f"\n→ {OUT}/schedule.json")


if __name__ == "__main__":
    main()
