#!/usr/bin/env python3
"""两次独立 run 的复现判读。

口径(先写死):
  主判据 = 逐轮配对的 GPU p50 比值 B/A,轮 = 重复单位(R=9)。
  噪声底 = 同一口径的 A'/A(A' 与 A 是同一条 pipeline 的复跑)。
  判有效应 = 两次 run 方向一致 且 每次 run 内 B/A 的配对符号检验显著
             且 中位效应量明显大于同格的 |1 − A'/A|。
"""
import json, math, statistics as st, sys

def signtest(diffs):
    n = sum(1 for x in diffs if x != 0)
    if n == 0: return 1.0
    k = sum(1 for x in diffs if x < 0)
    C = math.comb
    tail = sum(C(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)

def cell_stats(c):
    rA, rB, rA2 = c["round_gpu_p50_A"], c["round_gpu_p50_B"], c["round_gpu_p50_A2"]
    ba = [b / a for b, a in zip(rB, rA)]
    a2a = [x / a for x, a in zip(rA2, rA)]
    return ba, a2a

runs = [(name, json.load(open(p))) for name, p in
        [("run1", sys.argv[1]), ("run2", sys.argv[2])]]

print("=" * 96)
for name, d in runs:
    c = d["correctness"]
    print(f"{name}: {d['adapter'].strip()}")
    print(f"       {d['width']}x{d['height']}  K={d['K']} R={d['R']} warmup={d['warmup']}  "
          f"ts={d['timestamp_query']}  A==B bytes: {c['identical']} "
          f"(differing={c['differing_bytes']})  errors={'none' if not d['wgpu_errors'] else d['wgpu_errors'][:80]}")
print("=" * 96)
print()

names = [c["cell"] for c in runs[0][1]["cells"]]
hdr = (f"{'cell':<12}{'r_px':>6} | " +
       " | ".join(f"{n}: {'B/A':>7} {'A2/A':>7} {'p':>7} {'wins':>5}" for n, _ in runs) +
       " |  复现?")
print(hdr); print("-" * len(hdr))

verdicts = {}
for i, cname in enumerate(names):
    parts, meds, ps = [], [], []
    for name, d in runs:
        c = d["cells"][i]
        ba, a2a = cell_stats(c)
        diff = [x - y for x, y in zip(ba, a2a)]
        p = signtest(diff)
        wins = sum(1 for x in diff if x < 0)
        meds.append((st.median(ba), st.median(a2a)))
        ps.append(p)
        parts.append(f"{name}: {st.median(ba):7.4f} {st.median(a2a):7.4f} {p:7.4f} {wins:>2}/{len(diff)}")
    same_dir = all(m[0] < 1 for m in meds) or all(m[0] > 1 for m in meds)
    sig = all(p < 0.05 for p in ps)
    big = all(abs(1 - m[0]) > 2 * abs(1 - m[1]) for m in meds)
    v = "✅ 复现" if (same_dir and sig and big) else ("⚠️ 部分" if same_dir else "❌ 不复现")
    verdicts[cname] = (v, meds, ps)
    r = runs[0][1]["cells"][i]["quad_radius_px"]
    print(f"{cname:<12}{r:>6.2f} | " + " | ".join(parts) + f" |  {v}")

print()
print("效应量(两次 run 的 B/A 中位数平均;负 = B 更快)")
for cname, (v, meds, ps) in verdicts.items():
    avg = st.mean(m[0] for m in meds)
    floor = st.mean(abs(1 - m[1]) for m in meds)
    print(f"  {cname:<12} B 比 A 快 {100*(1-avg):+6.2f}%      噪声底 |1−A2/A| = {100*floor:.2f}%")

print()
print("阳性对照(A 在 N vs N/2,GPU p50;必须明显更快)")
for i, cname in enumerate(names):
    line = f"  {cname:<12}"
    for name, d in runs:
        c = d["cells"][i]
        f_, h = c["A_instanced_gpu_ms"]["p50"], c["positive_control_A_halfN_gpu_ms"]["p50"]
        line += f"  {name}: {h/f_:.3f} {'PASS' if h < 0.8*f_ else 'FAIL'}"
    print(line)

print()
print("热漂移(每格 A 的逐轮 GPU p50,首→末)")
for i, cname in enumerate(names):
    line = f"  {cname:<12}"
    for name, d in runs:
        v = d["cells"][i]["round_gpu_p50_A"]
        line += f"  {name}: {v[0]:7.2f}→{v[-1]:7.2f} ({100*(v[-1]/v[0]-1):+6.1f}%)"
    print(line)

print()
print("壁钟交叉校验(方向必须与 GPU 一致)")
for i, cname in enumerate(names):
    line = f"  {cname:<12}"
    for name, d in runs:
        c = d["cells"][i]
        ba = [b/a for b, a in zip(c["round_wall_p50_B"], c["round_wall_p50_A"])]
        line += f"  {name}: wall B/A={st.median(ba):.4f}"
    print(line)
