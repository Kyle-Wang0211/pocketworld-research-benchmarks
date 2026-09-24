# -*- coding: utf-8 -*-
"""官方第二套融合判据 filter_depth_dynamic (D2HC-RMVSNet 的 Dynamic Consistency Checking)
在我们的 ep0 深度图上跑一遍。

为什么值得跑: 09-13 定的多层根因是 filter.py 只数同意票、单一阈值 + 固定票数
(`geo_mask = geo_mask_sum >= 3`)。官方仓库里【一直带着】另一套判据, 阈值与票数成对滑动取并集:
    for i in range(dh_view_num, 11):
        mask_i = (dist < i/dh_dist) & (rdd < i/dh_rel_diff)
    geo_mask = (geo_mask_sum >= 10) or any(count_i >= i)
即"票少就得贴得极紧, 松一点就得更多票"。我们从没用过它。

🔴 一个数都不自己定: 这套判据的 (dh_view_num, dist, rel_diff) 是 Tanks&Temples 逐场景手调的,
官方没给"新场景怎么定"的规则。所以不挑不猜 —— 把官方发布过的 14 组【全部】各跑一遍,
每一组都指得到出处, 让用户的眼睛挑。

两套融合的光度门逐字相同 (method='casdiffmvs' 都是 conf0/1/2 三道 [0.3,0.5,0.5]),
唯一变量 = 几何判据。
"""
import os, sys, time
os.environ.setdefault("VAR_GATE", "0"); os.environ.setdefault("TEX_GATE", "0")
sys.path.insert(0, "/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth, filter_depth_dynamic
from plyfile import PlyData

OUT = "/root/lg_ep0"
PAIR = "/root/mvs_P16k"          # = infer_arm.sh 的 --testpath
DST = "/root/dyn_ply"
os.makedirs(DST, exist_ok=True)

# 官方 filter_depth_dynamic 里写死的 14 个 T&T 场景名 -> 各自一组 (dh_view_num, dist, rel_diff)
SCANS = ['Family', 'Francis', 'Horse', 'Lighthouse', 'M60', 'Panther', 'Playground',
         'Train', 'Auditorium', 'Ballroom', 'Courtroom', 'Museum', 'Palace', 'Temple']
TRIPLE = {'Family': (2, 12, 1600), 'Francis': (9, 8, 1600), 'Horse': (2, 4, 1300),
          'Lighthouse': (6, 8, 1600), 'M60': (4, 8, 1600), 'Panther': (3, 4, 1300),
          'Playground': (6, 8, 1600), 'Train': (3, 4, 1600), 'Auditorium': (2, 4, 1300),
          'Ballroom': (2, 4, 1300), 'Courtroom': (2, 4, 1300), 'Museum': (2, 4, 1300),
          'Palace': (2, 4, 1300), 'Temple': (1, 4, 1500)}


def npts(p):
    return len(PlyData.read(p)['vertex'].data)


def run(tag, fn):
    ply = os.path.join(DST, tag + ".ply")
    if os.path.exists(ply):
        return npts(ply), 0.0
    t0 = time.time()
    import contextlib, io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):       # 每视图一行日志, 吞掉
        fn(ply)
    return npts(ply), time.time() - t0


print("=" * 86, flush=True)
print("阳性对照: lg_ep0 用【现役】融合(filter_depth, thres=3)必须复现 ep0 那朵云", flush=True)
print("=" * 86, flush=True)
n, t = run("baseline_t3", lambda p: filter_depth(
    PAIR, OUT, p, 3, 1.0, 0.01, [0.3, 0.5, 0.5], "casdiffmvs", "general"))
REF = 36232793
print("现役融合 thres=3 : {:,} 点   (arm_full_ep0/pc_t3.ply = {:,})   {}   [{:.0f} s]".format(
    n, REF, "一致" if n == REF else "🔴 不一致 (差 {:+,})".format(n - REF), t), flush=True)
base = n

print(flush=True)
print("=" * 86, flush=True)
print("官方第二套判据 filter_depth_dynamic —— 14 组官方三元组全跑, 一个数都没自己定", flush=True)
print("=" * 86, flush=True)
print("%-12s %-22s %14s %10s %8s" % ("官方场景名", "(票数下限,dist,rel_diff)", "点数", "vs 现役", "秒"), flush=True)
for s in SCANS:
    try:
        n, t = run("dyn_" + s, lambda p, s=s: filter_depth_dynamic(
            s, PAIR, OUT, p, [0.3, 0.5, 0.5], "casdiffmvs", "general"))
        print("%-12s %-22s %14s %9.1f%% %8.0f" % (
            s, str(TRIPLE[s]), "{:,}".format(n), 100.0 * n / base - 100, t), flush=True)
    except Exception as e:
        print("%-12s %-22s  🔴 %s" % (s, str(TRIPLE[s]), repr(e)[:70]), flush=True)
print("DONE", flush=True)
