# -*- coding: utf-8 -*-
"""用官方分割模态确定「天空」标签 —— 帧配准修正版。

上一版失败的原因: 转换器 tartanair_to_blend.py:188 是 enumerate(keep), 输出【按保留帧从 0 重新连续编号】,
且有 bad-R 丢帧 (Gascola P002: 源 1960 -> 输出 1775)。我按帧号直配, 全配错了。

修正: seg zip 里自带 pose_lcam_front.txt。用【相机中心】把 输出帧 j ↔ 源帧 i 精确对回去:
  源:  world_T_cam = [Rotation.from_quat(row[3:]).as_matrix() @ NED_R_CAM | row[:3]]   (转换器 :110-111)
       => 相机中心 = row[:3]
  我们: cam.txt 的 extrinsic 是 world->cam, 中心 = -R^T t
每个 j 必须唯一匹配到一个 i, 且距离 ~0, 否则报错停下。

判据(先声明后检验): 某标签 L 同时满足
  召回 = P(seg==L | depth 在最远簇) >= 0.95   且   纯度 = P(depth 在最远簇 | seg==L) >= 0.95
"""
import os, sys, zipfile
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm
from scipy.spatial.transform import Rotation

NED_R_CAM = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=np.float64)   # 转换器文件头
PROBE = "/root/ta_seg_probe"
CROP_Y0, CROP_H = 80, 480          # tartanair_to_blend.py:136-137
OUT_W, OUT_H = 768, 576


def our_centers(scan_dir):
    fs = sorted(__import__("glob").glob(os.path.join(scan_dir, "cams", "*_cam.txt")))
    C = []
    for p in fs:
        L = open(p).read().strip().split("\n")
        E = np.array([[float(x) for x in L[i].split()] for i in range(1, 5)])
        R, t = E[:3, :3], E[:3, 3]
        C.append(-R.T @ t)
    return fs, np.array(C)


def src_centers(zf, env, diff, traj):
    name = "%s/Data_%s/%s/pose_lcam_front.txt" % (env, diff, traj)
    rows = np.array([[float(x) for x in ln.split()] for ln in
                     zf.read(name).decode().strip().split("\n")])
    return rows[:, :3]            # world_T_cam 的平移 = 相机中心


def probe(env, diff, traj, nmax=40):
    z = os.path.join(PROBE, env, "Data_%s" % diff, "seg_lcam_front.zip")
    if not os.path.exists(z):
        print("  %s/%s/%s : 无 seg zip" % (env, diff, traj)); return None
    zf = zipfile.ZipFile(z)
    scan = "/root/monotrain/ta_%s_%s_%s" % (env, diff, traj)
    if not os.path.isdir(scan):
        print("  %s : 无对应 scan" % scan); return None
    camfs, Cj = our_centers(scan)
    Ci = src_centers(zf, env, diff, traj)
    # 最近邻匹配 + 距离自证
    d2 = ((Cj[:, None, :] - Ci[None, :, :]) ** 2).sum(-1)
    m = d2.argmin(1)
    worst = float(np.sqrt(d2[np.arange(len(m)), m]).max())
    uniq = len(set(m.tolist()))
    print("  %-30s 输出 %4d 帧 / 源 %4d 帧 | 匹配唯一 %d | 最差距离 %.2e"
          % (env + "/" + diff + "/" + traj, len(Cj), len(Ci), uniq, worst))
    if worst > 1e-3 or uniq != len(m):
        print("     🔴 配准不可信, 跳过"); return None

    far_hist, all_hist = {}, {}
    step = max(1, len(camfs) // nmax)
    used = 0
    for j in range(0, len(camfs), step)[:nmax] if False else list(range(0, len(camfs), step))[:nmax]:
        i = int(m[j])
        png = "%s/Data_%s/%s/seg_lcam_front/%06d_lcam_front_seg.png" % (env, diff, traj, i)
        try:
            raw = zf.read(png)
        except KeyError:
            continue
        s = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
        if s is None:
            continue
        if s.ndim == 3:
            s = s[:, :, 0]
        s = s[CROP_Y0:CROP_Y0 + CROP_H, :]
        s = cv2.resize(s, (OUT_W, OUT_H), interpolation=cv2.INTER_NEAREST)
        d = np.array(read_pfm(os.path.join(scan, "rendered_depth_maps", "%08d.pfm" % j))[0])
        if s.shape != d.shape:
            continue
        used += 1
        fin = np.isfinite(d) & (d > 0)
        v = np.unique(np.sort(d[fin])); lv = np.log10(v[v > 0]); g = np.diff(lv)
        if g.size == 0:
            continue
        k = int(np.argmax(g))
        far = (d > v[k]) & fin if g[k] > 0.7 else np.zeros_like(fin)
        for lab, c in zip(*np.unique(s[fin], return_counts=True)):
            all_hist[int(lab)] = all_hist.get(int(lab), 0) + int(c)
        if far.any():
            for lab, c in zip(*np.unique(s[far], return_counts=True)):
                far_hist[int(lab)] = far_hist.get(int(lab), 0) + int(c)
    if not far_hist:
        print("     %d 帧无最远簇(室内?)" % used); return None
    tot = sum(far_hist.values())
    best = max(far_hist, key=far_hist.get)
    rec = far_hist[best] / tot
    pur = far_hist[best] / max(all_hist.get(best, 1), 1)
    print("     %2d 帧 | 天空候选标签 %3d | 召回 %.4f | 纯度 %.4f | %s"
          % (used, best, rec, pur, "✅ 认定" if rec >= .95 and pur >= .95 else "🔴 不达标"))
    return best, rec, pur


if __name__ == "__main__":
    out = {}
    for spec in sys.argv[1:]:
        env, diff, traj = spec.split(":")
        r = probe(env, diff, traj)
        if r:
            out[spec] = r
    if out:
        labs = sorted({v[0] for v in out.values()})
        print("\n认定的天空标签: %s ⇒ %s" % (labs, "全局同一值" if len(labs) == 1 else "逐环境不同"))
