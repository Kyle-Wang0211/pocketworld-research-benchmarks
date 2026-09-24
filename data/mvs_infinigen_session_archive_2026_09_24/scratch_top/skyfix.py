# -*- coding: utf-8 -*-
"""用 TartanAir V2 官方分割修正 cam.txt 的深度范围（方案 B）。

为什么要修: tartanair_to_blend.py:114-119 把官方 colmap2mvsnet.py 的 p1/p99 规则从【稀疏 SfM 点】
  照搬到【稠密深度图】。稀疏点里从来没有天空, 稠密图里有 => 44.38% 的 cam 文件 depth_max 被天空撑大,
  且 blend.py:136-139 的 mask 把天空当成有效监督(帧内中位 10.9% / 最差 81.2% 的像素)。

为什么不能用深度阈值修: 400 帧实测 16% 没有断崖(SoulCity 在 5 个相差 20 倍的切点下摆动 17 倍)
  => 切点是自由参数 => 禁止自研。

方案 B: 掩码来自【官方分割模态】seg_lcam_front, 不是阈值。
  - 天空标签逐环境不同, 用跨模态对应【识别】: 某标签 L 对「深度最远簇」的 召回>=0.95 且 纯度>=0.95。
    实测 Gascola=59 / WesternDesertTown=29 / AbandonedFactory2=171, 召回纯度均 ≈1.0000。
  - 识别只用有断崖的帧; 识别完成后掩码一律用 seg, 所以没有断崖的场景(SoulCity)也能正确处理。
  - 帧配准: seg zip 自带 pose_lcam_front.txt, 用相机中心把 输出帧 j <-> 源帧 i 对死(实测最差 5.7e-08)。

两个阶段:  --stage identify   逐环境定标签 + 出闸门报告
           --stage rewrite    重算 p1/p99 并改写 cam.txt 末行(格式不变, 仍 2 token)
改写前把所有旧值存进 /root/skyfix_backup.tsv, 可完整回滚。
"""
import argparse, glob, json, os, sys, zipfile
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

PROBE = "/root/ta_seg_probe"
MONO = "/root/monotrain"
CROP_Y0, CROP_H = 80, 480          # tartanair_to_blend.py:136-137
OUT_W, OUT_H = 768, 576
LABELS_JSON = "/root/sky_labels.json"
BACKUP = "/root/skyfix_backup.tsv"


def scans():
    out = []
    for d in sorted(os.listdir(MONO)):
        if not d.startswith("ta_"):
            continue
        env, diff, traj = d[3:].rsplit("_", 2)
        out.append((d, env, diff, traj))
    return out


def load_seg_zip(env, diff):
    p = os.path.join(PROBE, env, "Data_%s" % diff, "seg_lcam_front.zip")
    return zipfile.ZipFile(p) if os.path.exists(p) else None


def align(scan, zf, env, diff, traj):
    """返回 (cam 文件列表, j->i 映射)。配准不可信则返回 None。"""
    camfs = sorted(glob.glob(os.path.join(MONO, scan, "cams", "*_cam.txt")))
    C = []
    for p in camfs:
        L = open(p).read().strip().split("\n")
        E = np.array([[float(x) for x in L[i].split()] for i in range(1, 5)])
        C.append(-E[:3, :3].T @ E[:3, 3])
    Cj = np.array(C)
    name = "%s/Data_%s/%s/pose_lcam_front.txt" % (env, diff, traj)
    try:
        rows = np.array([[float(x) for x in ln.split()] for ln in
                         zf.read(name).decode().strip().split("\n")])
    except KeyError:
        return None
    Ci = rows[:, :3]
    d2 = ((Cj[:, None, :] - Ci[None, :, :]) ** 2).sum(-1)
    m = d2.argmin(1)
    if np.sqrt(d2[np.arange(len(m)), m]).max() > 1e-3 or len(set(m.tolist())) != len(m):
        return None
    return camfs, m


def read_seg(zf, env, diff, traj, i):
    png = "%s/Data_%s/%s/seg_lcam_front/%06d_lcam_front_seg.png" % (env, diff, traj, i)
    try:
        raw = zf.read(png)
    except KeyError:
        return None
    s = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if s is None:
        return None
    if s.ndim == 3:
        s = s[:, :, 0]
    s = s[CROP_Y0:CROP_Y0 + CROP_H, :]
    return cv2.resize(s, (OUT_W, OUT_H), interpolation=cv2.INTER_NEAREST)


def official_range(d, valid):
    """tartanair_to_blend.py:114-119 原式, 只是 valid 现在由 seg 决定。"""
    v = d[valid]
    if v.size < 100:
        return None
    s = np.sort(v.ravel())
    return float(s[int(len(s) * .01)]), float(s[int(len(s) * .99)])


# ---------------------------------------------------------------- identify
def identify(per_env_frames=60):
    res = {}
    by_env = {}
    for scan, env, diff, traj in scans():
        by_env.setdefault(env, []).append((scan, diff, traj))
    for env in sorted(by_env):
        far_hist, all_hist, used, gapped = {}, {}, 0, 0
        for scan, diff, traj in by_env[env]:
            if used >= per_env_frames:
                break
            zf = load_seg_zip(env, diff)
            if zf is None:
                continue
            a = align(scan, zf, env, diff, traj)
            if a is None:
                continue
            camfs, m = a
            step = max(1, len(camfs) // 12)
            for j in list(range(0, len(camfs), step))[:12]:
                s = read_seg(zf, env, diff, traj, int(m[j]))
                if s is None:
                    continue
                d = np.array(read_pfm(os.path.join(MONO, scan, "rendered_depth_maps", "%08d.pfm" % j))[0])
                if s.shape != d.shape:
                    continue
                used += 1
                fin = np.isfinite(d) & (d > 0)
                v = np.unique(np.sort(d[fin])); lv = np.log10(v[v > 0]); g = np.diff(lv)
                if g.size == 0:
                    continue
                k = int(np.argmax(g))
                if g[k] <= 0.7:
                    continue
                gapped += 1
                far = (d > v[k]) & fin
                for lab, c in zip(*np.unique(s[fin], return_counts=True)):
                    all_hist[int(lab)] = all_hist.get(int(lab), 0) + int(c)
                for lab, c in zip(*np.unique(s[far], return_counts=True)):
                    far_hist[int(lab)] = far_hist.get(int(lab), 0) + int(c)
        if not far_hist:
            print("  %-28s %3d 帧, %2d 帧有断崖 -> 无天空, 不需改" % (env, used, gapped))
            res[env] = None
            continue
        tot = sum(far_hist.values())
        # 天空可能被拆成多个标签(sky / cloud / ...)。取【只出现在远簇】的那一组:
        #   纯度(L) = P(far | seg==L) >= 0.95 的所有 L; 再要求这组的总召回 >= 0.95。
        # 这是同一判据的自然推广: 单标签是它的特例。
        S = sorted([L for L in far_hist if far_hist[L] / max(all_hist.get(L, 1), 1) >= 0.95],
                   key=lambda L: -far_hist[L])
        rec = sum(far_hist[L] for L in S) / tot if S else 0.0
        ok = bool(S) and rec >= 0.95
        top = sorted(far_hist, key=far_hist.get, reverse=True)[:3]
        detail = " ".join("%d(占远簇%.2f,纯度%.2f)" % (L, far_hist[L] / tot,
                          far_hist[L] / max(all_hist.get(L, 1), 1)) for L in top)
        print("  %-26s %2d有断崖 | 选中 %-14s 组召回 %.4f | %s"
              % (env, gapped, str(S[:4]), rec, "✅" if ok else "🔴 跳过"))
        if not ok:
            print("      远簇前三: %s" % detail)
        res[env] = S if ok else None
    json.dump(res, open(LABELS_JSON, "w"), indent=1)
    n_ok = sum(1 for v in res.values() if v is not None)
    print("\n写出 %s : %d/%d 个环境认定了天空标签" % (LABELS_JSON, n_ok, len(res)))


# ---------------------------------------------------------------- rewrite
def do_scan(args):
    scan, env, diff, traj, lab = args
    zf = load_seg_zip(env, diff)
    if zf is None:
        return (scan, 0, 0, [])
    a = align(scan, zf, env, diff, traj)
    if a is None:
        return (scan, 0, 0, [])
    camfs, m = a
    rows, changed = [], 0
    for j, cf in enumerate(camfs):
        d = np.array(read_pfm(os.path.join(MONO, scan, "rendered_depth_maps", "%08d.pfm" % j))[0])
        fin = np.isfinite(d) & (d > 0)
        s = read_seg(zf, env, diff, traj, int(m[j]))
        valid = fin & ~np.isin(s, lab) if (s is not None and s.shape == d.shape) else fin
        r = official_range(d, valid)
        if r is None:
            continue
        txt = open(cf).read()
        lines = txt.rstrip("\n").split("\n")
        old = lines[-1].strip()
        new = "%f %f" % r
        if old == new:
            continue
        rows.append("%s\t%s\t%s" % (cf, old, new))
        lines[-1] = new
        open(cf, "w").write("\n".join(lines) + "\n")
        changed += 1
    return (scan, len(camfs), changed, rows)


def rewrite(workers=16):
    labs = json.load(open(LABELS_JSON))
    todo = [(s, e, d, t, labs.get(e)) for s, e, d, t in scans() if labs.get(e) is not None]
    print("需处理 %d 个 scan (认定了天空标签的环境)" % len(todo))
    from multiprocessing import Pool
    tot_f = tot_c = 0
    with open(BACKUP, "w") as bk, Pool(workers) as pool:
        for k, (scan, nf, nc, rows) in enumerate(pool.imap_unordered(do_scan, todo)):
            tot_f += nf; tot_c += nc
            for r in rows:
                bk.write(r + "\n")
            if k % 40 == 0:
                print("  [%3d/%d] %-34s 帧 %4d 改 %4d  (累计 改 %d / 共 %d)"
                      % (k, len(todo), scan[:34], nf, nc, tot_c, tot_f), flush=True)
    print("\n完成: 共 %d 帧, 改写 %d 个 cam (%.2f%%)。旧值备份在 %s"
          % (tot_f, tot_c, 100 * tot_c / max(tot_f, 1), BACKUP))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["identify", "rewrite"])
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    if a.stage == "identify":
        identify()
    else:
        rewrite(a.workers)
