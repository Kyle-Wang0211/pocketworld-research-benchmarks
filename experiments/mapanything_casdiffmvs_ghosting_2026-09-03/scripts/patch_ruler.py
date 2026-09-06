p = "/root/cloud_ghost_ruler.py"
s = open(p).read()
if "thickness_m_p95" not in s:
    s = s.replace(
        '        "thickness_m_p50": float(np.median(thr)),',
        '        "thickness_m_p50": float(np.median(thr)),\n'
        '        "thickness_m_p95": float(np.percentile(thr, 95)),\n'
        '        "thickness_m_p99": float(np.percentile(thr, 99)),\n'
        '        "frac_neigh_thicker_than_2cm": float((thr > 0.02).mean()),\n'
        '        "frac_neigh_thicker_than_5cm": float((thr > 0.05).mean()),')
    i = s.index('    print("%-34s pts')
    j = s.index("Path(a.out).write_text")
    new = ('    print("%-16s thick p50 %5.1fmm  p95 %6.1fmm  p99 %6.1fmm  >2cm %.4f  >5cm %.4f  SPLIT %.4f" % (\n'
           '        name, r["thickness_m_p50"] * 1000, r["thickness_m_p95"] * 1000, r["thickness_m_p99"] * 1000,\n'
           '        r["frac_neigh_thicker_than_2cm"], r["frac_neigh_thicker_than_5cm"], r["split_frac"]), flush=True)\n')
    s = s[:i] + new + s[j:]
    open(p, "w").write(s)
    print("tail statistics added")
else:
    print("already patched")
