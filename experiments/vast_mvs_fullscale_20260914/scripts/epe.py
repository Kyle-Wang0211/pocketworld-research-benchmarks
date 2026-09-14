import re, collections, statistics
b=collections.defaultdict(lambda: collections.defaultdict(list))
pat=re.compile(r"Iter (\d+)/\d+.*epe:([\d.]+), err3:([\d.]+), err1:([\d.]+)")
for l in open("/root/train_v2b.log"):
    m=pat.search(l)
    if m:
        k=int(m.group(1))//5000
        b[k]["epe"].append(float(m.group(2)))
        b[k]["err3"].append(float(m.group(3)))
        b[k]["err1"].append(float(m.group(4)))
print("  迭代区间          n   epe中位   err3中位  err1中位")
for k in sorted(b):
    d=b[k]
    print("  %6d-%-6d %3d  %7.3f  %7.4f  %7.4f" % (k*5000, k*5000+4999, len(d["epe"]),
          statistics.median(d["epe"]), statistics.median(d["err3"]), statistics.median(d["err1"])))
