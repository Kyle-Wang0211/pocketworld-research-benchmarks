#!/usr/bin/env python3
"""run3 判读:① A/B 第三次复现 ② 排序 indirection 定价(乱序 vs 顺序)。

⚠️ ② 的口径弱点(先写死,免得看到数字再找说法):
   乱序格(第 3 格)跑在前、顺序格(第 6 格)跑在最后,那时机身最烫。
   两格**不是交替的**,所以热漂移混杂在里面,而且方向是**压低顺序格**。
   ⇒ 顺序若仍明显更快 = 下界,可用;打平或更慢 = 不能下结论。
   干净做法:把「乱序/顺序」做成第四个轮换标签,与 A/B/A′ 一起交替。
"""
import json, math, statistics as st, sys

def signtest(d):
    n = sum(1 for x in d if x); k = sum(1 for x in d if x < 0)
    return min(1.0, 2*sum(math.comb(n,i) for i in range(min(k,n-k)+1))/2**n) if n else 1.0

def rat(c):
    rA, rB, rA2 = c["round_gpu_p50_A"], c["round_gpu_p50_B"], c["round_gpu_p50_A2"]
    return ([b/a for b,a in zip(rB,rA)], [x/a for x,a in zip(rA2,rA)])

d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "run3.json"))
by = {c["cell"]: c for c in d["cells"]}

print(f"{d['adapter'].strip()}   K={d['K']} R={d['R']} warmup={d['warmup']}")
cr = d["correctness"]
print(f"正确性 A vs B:sha256 相同={cr['identical']}  差异字节={cr['differing_bytes']}  "
      f"Dawn 错误={'无' if not d['wgpu_errors'] else d['wgpu_errors'][:80]}")
print()

print("── ① A/B 第三次复现 ──")
print(f"{'格子':<16}{'order':>6}{'B/A':>9}{'A2/A':>8}{'p':>8}{'B 胜':>7}{'阳性对照':>10}")
for c in d["cells"]:
    ba, a2a = rat(c)
    diff = [x-y for x,y in zip(ba,a2a)]
    pc = c["positive_control_A_halfN_gpu_ms"]["p50"] / c["A_instanced_gpu_ms"]["p50"]
    seq = "顺序" if not c.get("order_shuffled", True) else "乱序"
    print(f"{c['cell']:<16}{seq:>6}{st.median(ba):>9.4f}{st.median(a2a):>8.4f}"
          f"{signtest(diff):>8.4f}{sum(1 for x in diff if x<0):>5}/9"
          f"{pc:>8.3f} {'PASS' if pc<0.8 else 'FAIL'}")

print()
print("── ② 排序 indirection 定价(同 N=4M、同 r=1.5px、同一批点,只差 order[]) ──")
a, b = by.get("N4M_r1.5"), by.get("N4M_r1.5_seq")
if not b:
    print("  顺序格缺失")
else:
    for arm, key in [("A instancing", "A_instanced_gpu_ms"),
                     ("B 顶点展开", "B_expanded_gpu_ms")]:
        sh, sq = a[key]["p50"], b[key]["p50"]
        print(f"  {arm:<14} 乱序 {sh:8.2f} ms   顺序 {sq:8.2f} ms   "
              f"顺序/乱序 = {sq/sh:.4f}  ({'顺序快 %.1f%%' % (100*(1-sq/sh)) if sq<sh else '顺序慢 %.1f%%' % (100*(sq/sh-1))})")
    print()
    print("  逐轮 A 的 GPU p50(看热态差多少 —— 这是上面那个比值的混杂项):")
    print("    乱序格: " + " ".join(f"{v:6.1f}" for v in a["round_gpu_p50_A"]))
    print("    顺序格: " + " ".join(f"{v:6.1f}" for v in b["round_gpu_p50_A"]))
    dr_a = 100*(a["round_gpu_p50_A"][-1]/a["round_gpu_p50_A"][0]-1)
    dr_b = 100*(b["round_gpu_p50_A"][-1]/b["round_gpu_p50_A"][0]-1)
    print(f"    格内漂移:乱序 {dr_a:+.1f}%   顺序 {dr_b:+.1f}%")
    # 用「顺序格首轮 vs 乱序格末轮」给一个对热态最不利的保守下界
    cons = b["round_gpu_p50_A"][0] / a["round_gpu_p50_A"][-1]
    print(f"    保守下界(顺序格首轮 ÷ 乱序格末轮)= {cons:.4f}")
    print()
    sh, sq = a["B_expanded_gpu_ms"]["p50"], b["B_expanded_gpu_ms"]["p50"]
    gain_seq = 1 - sq/sh
    gain_ab  = 1 - st.median(rat(a)[0])
    print(f"  ⇒ 量级对比:顺序 vs 乱序 = {100*gain_seq:+.1f}%,"
          f"instancing vs 顶点展开 = {100*gain_ab:+.1f}%"
          f"   倍数 = {abs(gain_seq/gain_ab):.1f}×" if gain_ab else "")

print()
print("── 热漂移全景(每格 A 的逐轮 GPU p50 首→末)──")
for c in d["cells"]:
    v = c["round_gpu_p50_A"]
    print(f"  {c['cell']:<16} {v[0]:7.2f} → {v[-1]:7.2f}  ({100*(v[-1]/v[0]-1):+6.1f}%)")
