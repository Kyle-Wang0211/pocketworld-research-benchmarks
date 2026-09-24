# -*- coding: utf-8 -*-
"""诊断: 自适应闸的 9 条分支在我们场景里到底哪几条在开火。

算法(filter.py:405-412): 对 i in [N0..10]
    mask_i = (重投影误差 < i/A) AND (相对深度差 < i/B)      <- 容差随 i 变松
    通过条件之一: 【通过 mask_i 的源视图数 >= i】             <- 要求随 i 变严
  最终 geo_mask = (geo_mask_sum >= 10) OR (任一 i 成立)

问题: 如果 20 个邻居里实际只有 6-7 个真看到同一块表面,
      那 i>=8 的分支永远不可能成立 => 我们等于只跑了半个算法。
判据: 逐分支的【通过像素数】与【边际贡献】(只有这条分支接受的像素)。

逐字复用上游 check_geometric_consistency_dynamic, 不重写几何。
"""
import os, sys, numpy as np
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import (check_geometric_consistency_dynamic, read_camera_parameters,
                    read_pfm, read_pair_file, read_img)

PAIRDIR = sys.argv[1]; OUT = sys.argv[2]; NREF = int(sys.argv[3]) if len(sys.argv) > 3 else 12
N0, A, B = 2, 4, 1300                      # Museum 室内三元组
PHOTO = [0.3, 0.5, 0.5]
pairs = read_pair_file(os.path.join(PAIRDIR, "pair.txt"))
step = max(1, len(pairs)//NREF)
sample = pairs[::step][:NREF]
print("pair 目录 %s, 每 ref %d 个 src, 抽 %d 个 ref\n" % (PAIRDIR, len(pairs[0][1]), len(sample)), flush=True)

BR = list(range(N0, 11))
tot_pass = np.zeros(len(BR)); tot_only = np.zeros(len(BR))
tot_top = 0.0; tot_any = 0.0; tot_px = 0.0
agree_hist = np.zeros(21)

for ref, srcs in sample:
    K, E, dmin, dmax = read_camera_parameters(os.path.join(OUT, 'cams/%08d_cam.txt' % ref))
    d0 = read_pfm(os.path.join(OUT, 'depth_est/%08d.pfm' % ref))[0]
    c0 = read_pfm(os.path.join(OUT, 'conf0/%08d.pfm' % ref))[0]
    c1 = read_pfm(os.path.join(OUT, 'conf1/%08d.pfm' % ref))[0]
    c2 = read_pfm(os.path.join(OUT, 'conf2/%08d.pfm' % ref))[0]
    photo = (c0 > PHOTO[0]) & (c1 > PHOTO[1]) & (c2 > PHOTO[2])
    sums = None; loose_sum = None
    for s in srcs:
        Ks, Es, _, _ = read_camera_parameters(os.path.join(OUT, 'cams/%08d_cam.txt' % s))
        ds = read_pfm(os.path.join(OUT, 'depth_est/%08d.pfm' % s))[0]
        masks, last, _, _, _ = check_geometric_consistency_dynamic(
            d0, K, E, ds, Ks, Es, [N0, A, B])
        m = np.stack(masks).astype(np.int16)
        sums = m if sums is None else sums + m
        loose_sum = last.astype(np.int16) if loose_sum is None else loose_sum + last.astype(np.int16)
    # 逐分支
    br = np.stack([sums[k] >= BR[k] for k in range(len(BR))])
    top = loose_sum >= 10
    anyb = br.any(0) | top
    for k in range(len(BR)):
        others = np.delete(br, k, axis=0).any(0) | top
        tot_pass[k] += float((br[k] & photo).sum())
        tot_only[k] += float((br[k] & ~others & photo).sum())
    tot_top += float((top & photo).sum()); tot_any += float((anyb & photo).sum())
    tot_px += float(photo.sum())
    h, _ = np.histogram(loose_sum[photo], bins=np.arange(22))
    agree_hist[:len(h)] += h

print("过光度闸的像素 %s;最终几何通过 %s (%.1f%%)\n"
      % (format(int(tot_px), ","), format(int(tot_any), ","), 100*tot_any/max(tot_px,1)))
print("  分支 i | 容差(px/相对深度) | 要求视图数 | 通过像素占比 | 【只有它接受】")
print("  " + "-"*72)
for k, i in enumerate(BR):
    print("  i=%-4d | %5.2f px / %.5f  | >= %-7d | %10.2f%% | %9.2f%%"
          % (i, i/A, i/B, i, 100*tot_pass[k]/max(tot_px,1), 100*tot_only[k]/max(tot_px,1)))
print("  %-6s | %-17s | >= %-7d | %10.2f%% |" % ("top", "2.50 px / 0.00769", 10, 100*tot_top/max(tot_px,1)))
print("\n实际同意的源视图数分布(最松容差下, 占过光度闸像素的%):")
tot = agree_hist.sum()
for v in range(21):
    if agree_hist[v] > 0:
        print("   %2d 个视图: %6.2f%%  %s" % (v, 100*agree_hist[v]/tot, "#"*int(60*agree_hist[v]/tot)))
cum = agree_hist[::-1].cumsum()[::-1]
print("\n  >= 2 个: %.1f%%   >= 4: %.1f%%   >= 6: %.1f%%   >= 8: %.1f%%   >= 10: %.1f%%"
      % tuple(100*cum[x]/tot for x in (2,4,6,8,10)))
