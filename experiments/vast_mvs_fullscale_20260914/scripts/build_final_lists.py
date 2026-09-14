"""最终训练/验证表:多域、不抽样、不挑室内、不含 Hypersim(待法务)。
val 从每个桶按 scan 留出,使 **val 的桶构成与 train 相同**;train∩val = 0。
确定性:random.Random(7)。"""
import os, random, collections
ROOT = "/root/monotrain"; L = "/root/diffmvs/lists/ours"
os.makedirs(L, exist_ok=True)
VAL_FRAC = 0.10                      # 官方无规定;取 10% 留出,标明是我们定的

def bucket(s):
    return "TartanAir" if s.startswith("ta_") else ("Hypersim" if s.startswith("hs_") else "BlendedMVG")
def ntup(s):
    p = f"{ROOT}/{s}/cams/pair.txt"
    return int(open(p).readline()) if os.path.exists(p) else 0

by = collections.defaultdict(list)
for d in sorted(os.listdir(ROOT)):
    if not os.path.isdir(f"{ROOT}/{d}"): continue
    b = bucket(d)
    if b == "Hypersim": continue       # 许可待定,本轮不用
    n = ntup(d)
    if n > 0: by[b].append((d, n))

rng = random.Random(7)
train, val = [], []
print("%-12s %6s %10s | %5s %9s | %5s %9s" % ("bucket","scans","tuples","valS","valT","trnS","trnT"))
for b in sorted(by):
    lst = by[b][:]; rng.shuffle(lst)
    target = VAL_FRAC * sum(n for _, n in lst)
    acc = 0; v = []
    for s, n in lst:
        if acc + n <= target: v.append((s, n)); acc += n
    vs = set(s for s, _ in v)
    t = [(s, n) for s, n in lst if s not in vs]
    val += v; train += t
    print("%-12s %6d %10s | %5d %9s | %5d %9s"
          % (b, len(lst), f"{sum(n for _,n in lst):,}", len(v), f"{acc:,}",
             len(t), f"{sum(n for _,n in t):,}"))

def report(name, items):
    T = sum(n for _, n in items)
    print("\n%s: %d scans / %s 组" % (name, len(items), f"{T:,}"))
    agg = collections.Counter()
    for s, n in items: agg[bucket(s)] += n
    for b in sorted(agg): print("   %-12s %9s  %5.2f%%" % (b, f"{agg[b]:,}", 100.0*agg[b]/T))
    return T

Tt = report("train", train); Tv = report("val", val)
print("\ntrain∩val = %d" % len(set(s for s,_ in train) & set(s for s,_ in val)))
print("val 占比 = %.2f%%" % (100.0*Tv/(Tt+Tv)))
open(f"{L}/train.txt","w").write("\n".join(sorted(s for s,_ in train))+"\n")
open(f"{L}/val.txt","w").write("\n".join(sorted(s for s,_ in val))+"\n")
print("写出", f"{L}/train.txt", "和", f"{L}/val.txt")
it = Tt // 4
print("⇒ %s 迭代/轮 × 0.355s = %.2f 小时/轮;16 轮 = %.1f 小时 (%.1f 天)"
      % (f"{it:,}", it*0.355/3600, 16*it*0.355/3600, 16*it*0.355/86400))
