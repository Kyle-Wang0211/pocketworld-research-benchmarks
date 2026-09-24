# -*- coding: utf-8 -*-
"""用官方分割模态确定「天空」标签 —— 跨模态交叉验证, 不拍阈值。

背景: TartanAir V2 的 seg_label_map.json 在 HF 仓和 AirLab Swift 桶里都不存在
      (visualizer.py:62 那个引用是给 TartanGround 用的)。所以标签 ID 得自己认。

判据(先声明, 后检验, 不事后挑):
  对每个环境, 找那个标签 L 使得
    召回 = P(seg==L | depth 属于最远那一簇)  要 >= 0.95
    纯度 = P(depth 属于最远那一簇 | seg==L)  要 >= 0.95
  两项同时达标才认定 L=天空。达不到就报告失败, 不硬认。
  「最远那一簇」只用来【认标签】, 认完之后掩码一律用 seg, 不再用深度阈值 ——
  这正是要解决 SoulCity 那类「深度没有断崖」的场景。

同时检查: 不同环境的天空标签是不是同一个值(若是, 更省事且更可信)。
"""
import glob, os, sys, zipfile, io
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

PROBE = "/root/ta_seg_probe"


def frames_for(env, diff):
    """返回 (seg_png_bytes, depth_pfm_path) 配对; 深度来自我们已转换好的 monotrain。"""
    z = os.path.join(PROBE, env, "Data_%s" % diff, "seg_lcam_front.zip")
    if not os.path.exists(z):
        return []
    zf = zipfile.ZipFile(z)
    out = []
    for n in zf.namelist():
        if not n.endswith("_seg.png"):
            continue
        parts = n.split("/")
        traj = parts[2]                      # P000
        idx = os.path.basename(n).split("_")[0]   # 000062
        dp = "/root/monotrain/ta_%s_%s_%s/rendered_depth_maps/%08d.pfm" % (env, diff, traj, int(idx))
        if os.path.exists(dp):
            out.append((zf, n, dp))
    return out


def analyse(env, diff, nmax=25):
    pairs = frames_for(env, diff)
    if not pairs:
        print("  %s/%s : 无配对帧" % (env, diff)); return None
    step = max(1, len(pairs) // nmax)
    far_hist, all_hist, near_hist = {}, {}, {}
    used = 0
    for zf, n, dp in pairs[::step][:nmax]:
        seg = cv2.imdecode(np.frombuffer(zf.read(n), np.uint8), cv2.IMREAD_UNCHANGED)
        d = np.array(read_pfm(dp)[0])
        if seg is None or seg.shape[:2] != (640, 640):
            continue
        # 我们的深度图是 640x640 中心裁 640x480 再缩到 768x576 (转换器注释), 这里把 seg 做同样处理
        s = seg[:, :, 0] if seg.ndim == 3 else seg
        s = s[80:560, :]                                    # 中心裁 640x480
        s = cv2.resize(s, (768, 576), interpolation=cv2.INTER_NEAREST)
        if s.shape != d.shape:
            continue
        used += 1
        fin = np.isfinite(d) & (d > 0)
        # 「最远一簇」: log 轴最大空档以上; 若无明显空档(<0.7 个数量级)则该帧不参与认标签
        v = np.unique(np.sort(d[fin]))
        lv = np.log10(v[v > 0])
        g = np.diff(lv)
        if g.size == 0:
            continue
        k = int(np.argmax(g))
        farmask = (d > v[k]) & fin if g[k] > 0.7 else np.zeros_like(fin)
        for lab, cnt in zip(*np.unique(s[fin], return_counts=True)):
            all_hist[int(lab)] = all_hist.get(int(lab), 0) + int(cnt)
        if farmask.any():
            for lab, cnt in zip(*np.unique(s[farmask], return_counts=True)):
                far_hist[int(lab)] = far_hist.get(int(lab), 0) + int(cnt)
    if not far_hist:
        print("  %s/%s : %d 帧无「最远簇」(可能室内无天空)" % (env, diff, used)); return None
    tot_far = sum(far_hist.values())
    best = max(far_hist, key=far_hist.get)
    recall = far_hist[best] / tot_far
    purity = far_hist[best] / max(all_hist.get(best, 1), 1)
    print("  %-30s %2d 帧 | 候选标签 %3d | 召回 %.4f | 纯度 %.4f | %s"
          % (env + "/" + diff, used, best, recall, purity,
             "✅ 认定" if (recall >= 0.95 and purity >= 0.95) else "🔴 不达标"))
    return best, recall, purity


if __name__ == "__main__":
    print("环境/难度                        帧数 | 天空候选 | 召回 | 纯度")
    res = {}
    for spec in sys.argv[1:]:
        env, diff = spec.split(":")
        r = analyse(env, diff)
        if r:
            res[spec] = r
    labs = {v[0] for v in res.values()}
    print("\n各环境认定的天空标签值: %s  ⇒ %s"
          % (sorted(labs), "全局同一个值" if len(labs) == 1 else "逐环境不同, 必须逐环境认"))
