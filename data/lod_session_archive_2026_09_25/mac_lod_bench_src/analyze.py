#!/usr/bin/env python3
"""pw_splat_ab 结果判读。

判读规矩(先写死,免得看到数字再挑口径):
  1. 主判据 = GPU 时间戳的 p50(排除 CPU encode 与 submit/wait 开销)。
     壁钟 p50 作为交叉校验;两者若不同向,以「不结论」处理。
  2. 效应量 = 逐轮配对比值 B/A(轮 = 重复单位,不是帧 —— 同一轮内的 50 帧
     是伪重复)。报告 9 轮配对比值的中位数与全距。
  3. 噪声底 = A' / A 的同一口径配对比值。A'与 A 是同一条 pipeline,
     所以它量到的任何偏离 1.0 都是本流程分辨不了的部分。
  4. **只有 |1 - B/A| 明显大于 |1 - A'/A| 才算「有效应」。**
  5. 阳性对照:A 在 N/2 上必须明显快于 N。不过就宣告尺子坏了,全部作废。
"""
import json, statistics, sys

path = sys.argv[1] if len(sys.argv) > 1 else "full.json"
d = json.load(open(path))

print(f"adapter        : {d['adapter']}")
print(f"target         : {d['width']}x{d['height']}  timestamp_query={d['timestamp_query']}")
print(f"schedule       : K={d['K']} frames/block, R={d['R']} rounds, warmup={d['warmup']}")
print(f"armA wgsl sha  : {d['armA_wgsl_sha256'][:16]}…")
print(f"armB wgsl sha  : {d['armB_wgsl_sha256'][:16]}…")
c = d["correctness"]
print(f"correctness    : A==B bytes? {c['identical']}  differing={c['differing_bytes']}  maxabs={c['max_abs_diff']}")
if d.get("wgpu_errors"):
    print(f"wgpu errors    : {d['wgpu_errors'][:200]}")
print()

def paired(num, den):
    """逐轮配对比值。"""
    return [n / v for n, v in zip(num, den) if v > 0]

hdr = (f"{'cell':<12}{'r_px':>6}{'A gpu p50':>11}{'B gpu p50':>11}"
       f"{'B/A':>9}{'A2/A':>9}{'verdict':>12}")
print(hdr); print("-" * len(hdr))

rows = []
for cell in d["cells"]:
    A  = cell["A_instanced_gpu_ms"]["p50"]
    B  = cell["B_expanded_gpu_ms"]["p50"]
    A2 = cell["A2_instanced_gpu_ms"]["p50"]
    rA, rB, rA2 = (cell["round_gpu_p50_A"], cell["round_gpu_p50_B"],
                   cell["round_gpu_p50_A2"])
    ba  = paired(rB, rA)
    a2a = paired(rA2, rA)
    ba_med  = statistics.median(ba)  if ba  else float("nan")
    a2a_med = statistics.median(a2a) if a2a else float("nan")
    effect = abs(1 - ba_med)
    floor  = abs(1 - a2a_med)
    # 效应必须至少是噪声底的 2 倍,且 B/A 的全距不能跨过 1.0
    crosses_one = ba and (min(ba) < 1.0 < max(ba))
    if effect > max(2 * floor, 0.01) and not crosses_one:
        verdict = "B faster" if ba_med < 1 else "B SLOWER"
    else:
        verdict = "no effect"
    rows.append((cell, ba, a2a, ba_med, a2a_med, verdict))
    print(f"{cell['cell']:<12}{cell['quad_radius_px']:>6.2f}"
          f"{A:>11.3f}{B:>11.3f}{ba_med:>9.4f}{a2a_med:>9.4f}{verdict:>12}")

print()
print("逐轮配对比值(轮 = 重复单位;全距跨过 1.0 = 方向都不稳)")
for cell, ba, a2a, ba_med, a2a_med, verdict in rows:
    print(f"  {cell['cell']:<12} B/A  med={ba_med:.4f}  range=[{min(ba):.4f},{max(ba):.4f}]  n={len(ba)}")
    print(f"  {'':<12} A2/A med={a2a_med:.4f}  range=[{min(a2a):.4f},{max(a2a):.4f}]  n={len(a2a)}")

print()
print("阳性对照(同一把尺子,A 在 N 与 N/2;必须明显更快)")
for cell in d["cells"]:
    full = cell["A_instanced_gpu_ms"]["p50"]
    half = cell["positive_control_A_halfN_gpu_ms"]["p50"]
    ok = half < full * 0.8
    print(f"  {cell['cell']:<12} N={full:8.3f} ms  N/2={half:8.3f} ms  "
          f"ratio={half/full:.3f}  {'PASS' if ok else 'FAIL — 尺子坏了'}")

print()
print("热漂移诊断(每轮 A 的 GPU p50;单调上升 = 在降频,交替设计正在起作用)")
for cell in d["cells"]:
    v = cell["round_gpu_p50_A"]
    print(f"  {cell['cell']:<12} " + " ".join(f"{x:.2f}" for x in v)
          + f"   drift={100*(v[-1]/v[0]-1):+.1f}%")

print()
print("壁钟交叉校验(含 CPU encode + submit/wait;方向必须与 GPU 一致)")
for cell in d["cells"]:
    rA, rB = cell["round_wall_p50_A"], cell["round_wall_p50_B"]
    ba = paired(rB, rA)
    print(f"  {cell['cell']:<12} wall B/A med={statistics.median(ba):.4f}  "
          f"A p50={cell['A_instanced_wall_ms']['p50']:.3f} ms  "
          f"B p50={cell['B_expanded_wall_ms']['p50']:.3f} ms")
