# -*- coding: utf-8 -*-
"""阴性对照: 把 thres=2 【随机】抽稀到与自适应档完全相同的点数。
问题: layerruler 的 MINPTS=4 要求像素内至少 4 个点才参与统计 =>
      任何"少扔点"的闸都会机械性地让尺子变好。必须问:
      "如果我随机扔掉同样多的点, 尺子会变好多少?"
判据: 自适应档必须【显著优于】随机扔同样多点, 否则它的优势就是密度假象。
🔴 这是第 5 次防这个坑(前 4 次: 指标放行了肉眼否决的东西)。
"""
import numpy as np, os
SRC, N_TARGET, TAG = "/root/bins_gm/GM_t2", 28213257, "GM_rnd"
pos = np.fromfile(SRC + ".pos", dtype="<f4").reshape(-1, 3)
col = np.fromfile(SRC + ".col", dtype=np.uint8).reshape(-1, 3)
n = pos.shape[0]
rng = np.random.default_rng(0)                    # 固定种子, 可复现
keep = rng.permutation(n)[:N_TARGET]
keep.sort()                                       # 保持原顺序, 不改空间分布
pos[keep].tofile("/root/bins_gm/%s.pos" % TAG)
col[keep].tofile("/root/bins_gm/%s.col" % TAG)
print("  %s: %s -> %s 点 (与 GM_dyn 完全相同)" % (TAG, format(n, ","), format(N_TARGET, ",")))
