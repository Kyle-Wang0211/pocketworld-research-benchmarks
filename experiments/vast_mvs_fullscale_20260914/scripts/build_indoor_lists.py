import os, re, collections, json
ROOT = "/root/monotrain"
INDOOR = {"AbandonedFactory2","AmericanDiner","ArchVizTinyHouseDay","ArchVizTinyHouseNight",
          "CarWelding","CountryHouse","Hospital","House","Office","OldBrickHouseDay",
          "OldBrickHouseNight","Restaurant","RetroOffice","Supermarket"}
BAD = set(l.strip() for l in open("/root/bad_val_scans.txt") if l.strip())

def ntup(s):
    p = f"{ROOT}/{s}/cams/pair.txt"
    return int(open(p).readline()) if os.path.exists(p) else 0

ta_in, ta_out, mvg, hs = [], [], [], []
for d in sorted(os.listdir(ROOT)):
    n = ntup(d)
    if n == 0: continue
    if d.startswith("ta_"):
        e = re.sub(r"_(easy|hard)_P\d+$", "", d[3:])
        (ta_in if e in INDOOR else ta_out).append((d, n))
    elif d.startswith("hs_"): hs.append((d, n))
    else: mvg.append((d, n))

def tot(x): return sum(n for _, n in x)
print("盘上全部可用:")
for name, lst in (("TartanAir 室内", ta_in), ("TartanAir 室外", ta_out),
                  ("BlendedMVG", mvg), ("Hypersim(不用)", hs)):
    print("  %-18s %4d scans  %9s 组" % (name, len(lst), f"{tot(lst):,}"))
print("  已知坏 scan 黑名单 %d 个" % len(BAD))

ta_in = [(s, n) for s, n in ta_in if s not in BAD]
mvg   = [(s, n) for s, n in mvg   if s not in BAD]
T = tot(ta_in) + tot(mvg)
print("\n方案B(不抽样,全用上) = TartanAir室内 + BlendedMVG")
print("  室内     %4d scans %9s 组  %5.2f%%" % (len(ta_in), f"{tot(ta_in):,}", 100.0*tot(ta_in)/T))
print("  BlendedMVG %2d scans %9s 组  %5.2f%%" % (len(mvg), f"{tot(mvg):,}", 100.0*tot(mvg)/T))
print("  合计       %4d scans %9s 组" % (len(ta_in)+len(mvg), f"{T:,}"))
it = T // 4
print("  ⇒ %s 迭代/轮 × 0.355s = %.2f 小时/轮 ;16 轮 = %.1f 小时 (%.1f 天)"
      % (f"{it:,}", it*0.355/3600, 16*it*0.355/3600, 16*it*0.355/86400))
json.dump({"ta_in":[s for s,_ in ta_in], "mvg":[s for s,_ in mvg]},
          open("/root/indoor_pool.json","w"))
