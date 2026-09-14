"""数据卫生预扫:不靠崩来发现坏 scan。
判据无自定阈值 —— depth_min/depth_max 必须是有限正数且 max>min;
额外排除 65504.0(fp16 上限哨兵,不是真实深度)。
blend.py 读的是 cam 文件第 11 行(0-based)。"""
import os, math, json, collections
ROOT = "/root/monotrain"
SENTINEL = 65504.0

def check_scan(s):
    cams = f"{ROOT}/{s}/cams"
    if not os.path.isdir(cams): return "no_cams", 0, 0
    bad = 0; tot = 0
    for f in sorted(os.listdir(cams)):
        if not f.endswith("_cam.txt"): continue
        tot += 1
        try:
            L = open(f"{cams}/{f}").read().split("\n")
            v = L[11].split()
            a, b = float(v[0]), float(v[-1])
        except Exception:
            bad += 1; continue
        dmin, dmax = min(a, b), max(a, b)
        if not (math.isfinite(dmin) and math.isfinite(dmax)): bad += 1; continue
        if dmin <= 0 or dmax <= dmin: bad += 1; continue
        if dmin == SENTINEL or dmax == SENTINEL: bad += 1; continue
    return ("ok" if bad == 0 else "bad"), bad, tot

def bucket(s):
    return "TartanAir" if s.startswith("ta_") else ("Hypersim" if s.startswith("hs_") else "BlendedMVG")

res = collections.defaultdict(list); badlist = []
scans = sorted(d for d in os.listdir(ROOT) if os.path.isdir(f"{ROOT}/{d}"))
for i, s in enumerate(scans):
    st, bad, tot = check_scan(s)
    res[bucket(s)].append((s, st, bad, tot))
    if st != "ok": badlist.append((s, st, bad, tot))
    if i and i % 400 == 0: print("  %d/%d  坏 %d" % (i, len(scans), len(badlist)), flush=True)

print("\n%-12s %6s %6s %6s" % ("bucket", "scans", "ok", "bad"))
for b, v in sorted(res.items()):
    print("%-12s %6d %6d %6d" % (b, len(v), sum(1 for x in v if x[1]=="ok"), sum(1 for x in v if x[1]!="ok")))
print("\n坏 scan %d 个,前 20:" % len(badlist))
for s, st, bad, tot in badlist[:20]: print("   %-42s %-8s %d/%d 帧坏" % (s, st, bad, tot))
json.dump([s for s,_,_,_ in badlist], open("/root/hygiene_bad_scans.json","w"))
print("\n写出 /root/hygiene_bad_scans.json")
