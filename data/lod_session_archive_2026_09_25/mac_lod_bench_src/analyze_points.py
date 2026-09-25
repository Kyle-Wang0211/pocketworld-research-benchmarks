#!/usr/bin/env python3
"""裸点云台架判读。判读规矩先写死,免得看到数字再挑口径。

  1. 主判据 = GPU 时间戳 p50(排除 CPU encode / submit / wait)。壁钟作交叉校验。
  2. 效应量 = **逐轮配对比值**(轮 = 重复单位;同一轮内的 K 帧是伪重复)。
  3. 噪声底 = P2/P 的同口径配对比值 —— P2 与 P 是同一条 pipeline、同一个 draw,
     所以它偏离 1.0 多少就是这套机器分辨不了的下限。只有效应明显大于它才算数。
  4. 阳性对照:P 在 N/2 上必须 ≈0.5。不过 ⇒ 尺子坏了(多半是降频),整格作废。
  5. R 小的时候符号检验 p 下限就是 2/2^R(R=5 ⇒ 0.0625),p<0.05 结构上不可达
     ⇒ 小 R 的判据是「全胜 + 全距不跨 1.0 + 远高于噪声底」,不是 p 值。
"""
import json, statistics, sys, glob

def paired(num, den):
    return [n / d for n, d in zip(num, den) if d > 0]

def fmt(v, w=8, p=2):
    return f"{v:{w}.{p}f}"

files = sys.argv[1:] or sorted(glob.glob("points_run*.json"))
for path in files:
    d = json.load(open(path))
    print("=" * 78)
    print(f"{path}   tag={d['tag']}")
    print(f"adapter   : {d['adapter']}")
    print(f"target    : {d['width']}x{d['height']}  ts_query={d['timestamp_query']}  "
          f"r={d['quad_radius_px']}px")
    print(f"schedule  : K={d['K']} R={d['R']} warm={d['warmup']} cell={d['cell_sel']} "
          f"dropped_mask={d['dropped_labels_mask']}")
    if d.get("wgpu_errors"):
        print(f"!! wgpu errors: {d['wgpu_errors'][:300]}")
    for cell in d["cells"]:
        n = cell["n"]
        print(f"\n--- cell {cell['cell']}  N={n:,}  labels={cell['labels']}")
        base = cell["P_gpu_ms"]["p50"]
        hdr = f"{'label':<6}{'gpu p50':>10}{'wall p50':>10}{'ms/1M pt':>10}{'fps(gpu)':>10}{'/P':>8}"
        print(hdr); print("-" * len(hdr))
        for L in cell["labels"]:
            g = cell[L + "_gpu_ms"]["p50"]; w = cell[L + "_wall_ms"]["p50"]
            print(f"{L:<6}{fmt(g,10,3)}{fmt(w,10,3)}"
                  f"{fmt(g/(n/1e6),10,3)}{fmt(1000.0/w,10,1)}{fmt(g/base,8,4)}")
        emp = cell.get("empty_pass_gpu_ms", {}).get("p50", float('nan'))
        print(f"empty pass (1 point, same pipeline/pass): {emp:.3f} ms  "
              f"= {100*emp/base:.2f}% of P")
        half = cell["positive_control_P_halfN_gpu_ms"]["p50"]
        ratio = half / base
        verdict = "PASS" if 0.35 <= ratio <= 0.70 else "**FAIL -> discard cell**"
        print(f"positive control P(N/2)/P(N) = {half:.3f}/{base:.3f} = {ratio:.4f}  {verdict}")
        # 逐轮配对
        print(f"{'contrast':<16}{'median':>9}{'min':>9}{'max':>9}{'wins':>8}{'note':>10}")
        rP = cell.get("round_gpu_p50_P", [])
        floor = None
        for L in cell["labels"]:
            if L == "P": continue
            r = paired(cell.get("round_gpu_p50_" + L, []), rP)
            if not r: continue
            med = statistics.median(r)
            wins = sum(1 for x in r if x < 1.0)
            note = "NOISE FLOOR" if L == "P2" else ""
            if L == "P2": floor = abs(1 - med)
            print(f"{L+'/P':<16}{fmt(med,9,4)}{fmt(min(r),9,4)}{fmt(max(r),9,4)}"
                  f"{wins:>5}/{len(r):<2}{note:>10}")
        if floor is not None:
            print(f"noise floor |1-P2/P| = {100*floor:.2f}%")
        # 漂移:每个标签第一轮 vs 最后一轮
        drift = []
        for L in cell["labels"]:
            s = cell.get("round_gpu_p50_" + L, [])
            if len(s) >= 2 and s[0] > 0:
                drift.append(f"{L} {100*(s[-1]/s[0]-1):+.1f}%")
        print("round1 -> roundR drift: " + "  ".join(drift))
    o = d.get("correctness_order_independence")
    if o:
        print(f"\n正确性(排序能不能删):同一批点换 buffer 次序各画一遍")
        print(f"  identical={o['identical']}  differing_bytes={o['differing_bytes']}  "
              f"max_abs={o['max_abs_diff']}")
        print(f"  coverage {o['order1']['coverage']:.6f} vs 解析期望 "
              f"{o['expected_coverage']:.6f}   sd_rgb={o['order1']['sd_rgb']}")
    rb = d.get("correctness_reordered_buffers")
    if rb:
        print(f"正确性(**计时用的那两个重排 buffer 本身**,画出来比 sha256):")
        print(f"  quad screen-order == reference : {rb['quad_scr_matches']}")
        print(f"  quad morton-order == reference : {rb['quad_mor_matches']}")
        print(f"  pointlist morton coverage      : {rb['pointlist_morton_coverage']:.6f}"
              f"   sha={rb['pointlist_morton_sha256'][:16]}…")
    pl = d.get("correctness_pointlist_order")
    if pl:
        print(f"正确性(PointList 通路,PT vs PTm 只差 buffer 次序):")
        print(f"  identical={pl['identical']}  differing_bytes={pl['differing_bytes']}")
        print(f"  coverage {pl['order1']['coverage']:.6f} / {pl['order2']['coverage']:.6f}"
              f"  vs 解析期望 {pl['expected_coverage']:.6f}"
              f"   sd_rgb={pl['order1']['sd_rgb']}")
    ncl = d.get("negative_control_blended_order")
    if ncl:
        print(f"阴性对照(混合+无深度,必须**不同**,否则判据不会失败):")
        print(f"  identical={ncl['identical']}  differing_bytes={ncl['differing_bytes']}  "
              f"max_abs={ncl['max_abs_diff']}")
