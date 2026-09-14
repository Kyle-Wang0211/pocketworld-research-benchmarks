"""只删「参考视图坏」的那几组,保留同 scan 其余全部。
依据: diffmvs/datasets/blend.py 里 depth_min/max 仅在 if i==0 分支使用(源视图的深度范围未被读取)。
判据零自由参数: dmin/dmax 必须有限、正、max>min,且不等于 fp16 哨兵 65504.0。
原 pair.txt 备份为 pair.txt.orig,可逐字还原。"""
import os, math, json, shutil
ROOT = "/root/monotrain"; SENT = 65504.0

def ref_ok(scan, vid):
    p = f"{ROOT}/{scan}/cams/{vid:0>8}_cam.txt"
    try:
        L = open(p).read().split("\n"); v = L[11].split()
        a, b = float(v[0]), float(v[-1])
    except Exception:
        return False
    dmin, dmax = min(a, b), max(a, b)
    return (math.isfinite(dmin) and math.isfinite(dmax) and dmin > 0
            and dmax > dmin and dmin != SENT and dmax != SENT)

bad_scans = json.load(open("/root/hygiene_bad_scans.json"))
tot_before = tot_after = 0; touched = 0
for s in bad_scans:
    p = f"{ROOT}/{s}/cams/pair.txt"
    if not os.path.exists(p): print("  跳过(无 pair.txt):", s); continue
    src = p + ".orig"
    if not os.path.exists(src): shutil.copy(p, src)
    L = [l.rstrip("\n") for l in open(src)]
    n = int(L[0].strip()); kept = []
    for i in range(n):
        ref = L[1 + 2*i].strip(); srcs = L[2 + 2*i]
        if ref_ok(s, int(ref)): kept.append((ref, srcs))
    tot_before += n; tot_after += len(kept); touched += 1
    with open(p, "w") as f:
        f.write("%d\n" % len(kept))
        for ref, srcs in kept: f.write(ref + "\n" + srcs + "\n")
    print("  %-42s %4d -> %4d 组 (-%d)" % (s, n, len(kept), n - len(kept)))
print("\n处理 %d 个 scan;组数 %s -> %s,共删 %s 组 (%.3f%%)"
      % (touched, f"{tot_before:,}", f"{tot_after:,}", f"{tot_before-tot_after:,}",
         100.0*(tot_before-tot_after)/max(tot_before,1)))
