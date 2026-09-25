#!/usr/bin/env python3
"""run4 判读:2×2 析因(draw 拓扑 × order 访存)+ 噪声底。

五个标签在轮内循环轮换,所以**每一组对比**都在轮内配对,热漂移对所有
对比同等平衡 —— 不再像 run3 那样只有 A/B 受保护。

判读规矩(先写死):
  - 所有比值都做在轮中位数的**逐轮配对**上(轮 = 重复单位,R=10)。
  - 噪声底 = A2_shuf / A_shuf(同 pipeline 同 order,只差位置)。
  - 任何一组效应必须 |1−ratio| 明显大于同格噪声底才算数。
"""
import json, math, statistics as st, sys

def signtest(d):
    n = sum(1 for x in d if x); k = sum(1 for x in d if x < 0)
    return min(1.0, 2*sum(math.comb(n,i) for i in range(min(k,n-k)+1))/2**n) if n else 1.0

def paired(c, num, den):
    a, b = c[f"round_gpu_p50_{den}"], c[f"round_gpu_p50_{num}"]
    return [y/x for x, y in zip(a, b) if x > 0]

d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "run4.json"))
print(f"{d['adapter'].strip()}")
print(f"K={d['K']} R={d['R']} warmup={d['warmup']}  "
      f"正确性 A vs B: sha256 相同={d['correctness']['identical']} "
      f"差异字节={d['correctness']['differing_bytes']}  "
      f"Dawn 错误={'无' if not d['wgpu_errors'] else d['wgpu_errors'][:60]}")
print()

COMPS = [
    ("噪声底",            "A2_shuf", "A_shuf", "同 pipeline 同 order,只差位置"),
    ("draw 拓扑(乱序)",  "B_shuf",  "A_shuf", "instancing → 顶点展开"),
    ("draw 拓扑(顺序)",  "B_seq",   "A_seq",  "同上,在顺序 order 下"),
    ("order 访存(A)",    "A_seq",   "A_shuf", "乱序 → 顺序,instancing 下"),
    ("order 访存(B)",    "B_seq",   "B_shuf", "乱序 → 顺序,顶点展开下"),
    ("两项合计",          "B_seq",   "A_shuf", "生产现状 → 两项都改"),
]

for c in d["cells"]:
    print(f"═══ {c['cell']}  N={c['n']:,}  r={c['quad_radius_px']:.2f}px ═══")
    print(f"  {'绝对值 GPU p50':<20}" + "  ".join(
        f"{n}={c[n+'_gpu_ms']['p50']:7.2f}ms" for n in
        ["A_shuf","B_shuf","A2_shuf","A_seq","B_seq"]))
    print()
    floor = abs(1 - st.median(paired(c, "A2_shuf", "A_shuf")))
    print(f"  {'对比':<18}{'比值中位':>10}{'效应':>9}{'全距':>19}{'p':>8}{'判':>10}")
    for name, num, den, _note in COMPS:
        v = paired(c, num, den)
        m = st.median(v)
        wins = sum(1 for x in v if x < 1)
        p = signtest([x - 1 for x in v])
        if name == "噪声底":
            verdict = "—"
        elif abs(1-m) > max(2*floor, 0.01) and p < 0.05:
            verdict = "更快" if m < 1 else "更慢"
        else:
            verdict = "无效应"
        print(f"  {name:<18}{m:>10.4f}{100*(1-m):>+8.1f}%"
              f"  [{min(v):.4f},{max(v):.4f}]{p:>8.4f}{verdict:>10}"
              f"  {wins}/{len(v)}")
    print(f"  (噪声底 |1−A2/A| = {100*floor:.2f}%)")
    print()
    print("  逐轮 GPU p50(看热漂移 —— 五个标签都在轮内,所以对所有对比同等):")
    for n in ["A_shuf","B_shuf","A2_shuf","A_seq","B_seq"]:
        v = c[f"round_gpu_p50_{n}"]
        print(f"    {n:<9}" + " ".join(f"{x:6.1f}" for x in v)
              + f"   漂移 {100*(v[-1]/v[0]-1):+5.1f}%")
    print(f"  阳性对照 N/2÷N = "
          f"{c['positive_control_A_halfN_gpu_ms']['p50']/c['A_shuf_gpu_ms']['p50']:.3f}")
    print()
