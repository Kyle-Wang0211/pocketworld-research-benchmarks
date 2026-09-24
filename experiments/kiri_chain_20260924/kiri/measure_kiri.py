# Same rulers as measure_both.py (layer2F / tri_stats_ply / manifold), for the two KIRI-chain meshes; A reused from measure_both.json.
import re, subprocess, json
PY = "/venv/main/bin/python"
MESHES = {"k1": "/root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply", "k3": "/root/tsdf_improve/kiri/out/kiri_v0.003_t0.04_w5.ply"}
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True); return "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Warning" not in l)
res = {"a": json.load(open("/root/tsdf_improve/four/meas/measure_both.json"))["a"]}
for k, m in MESHES.items():
    o = {}
    t = run([PY, "/root/tsdf/layer2F.py", m, f"L2F:{k}"]); o["raw_l2f"] = t
    g = re.search(r"([\d,]+)v\s+([\d,]+)f\s+面积\s+([\d.]+)m²\s+双层\(>2cm\)\s+([\d.]+)%\s+间距中位\s+([\d.]+)mm\s+最长边max\s+([\d.]+)mm", t)
    o.update(v=int(g[1].replace(",", "")), f=int(g[2].replace(",", "")), area=float(g[3]), dbl=float(g[4]), gap=float(g[5]), emax=float(g[6]))
    t = run([PY, "/root/tsdf/tri_stats_ply.py", m]); o["raw_tri"] = t
    g = re.search(r"最长边 mm\s+p50 ([\d.]+)\s+p90 ([\d.]+)\s+p99 ([\d.]+)", t); o.update(e50=float(g[1]), e99=float(g[3]))
    t = run([PY, "/root/tsdf/manifold.py", m]); o["raw_man"] = t
    g = re.search(r"非流形边\(>2面\) ([\d,]+)", t); o["nm"] = int(g[1].replace(",", ""))
    g = re.search(r"边界边 ([\d,]+) \(([\d.]+)% of edges\)\s+边界回路 ([\d,]+)", t); o.update(bnd=int(g[1].replace(",", "")), loops=int(g[3].replace(",", "")))
    g = re.search(r"连通分量 ([\d,]+)", t); o["cc"] = int(g[1].replace(",", ""))
    res[k] = o; print(k, {x: y for x, y in o.items() if not x.startswith("raw")}, flush=True)
rows = [("顶点", "v"), ("三角", "f"), ("总面积 m²", "area"), ("双层率(间距>2cm)", "dbl", 1), ("双层间距中位 mm", "gap"),
        ("边界回路数(≈洞+外缘)", "loops"), ("边界边", "bnd"), ("非流形边", "nm"), ("连通分量", "cc"), ("三角最长边 p50 mm", "e50"), ("三角最长边 p99 mm", "e99")]
st = {"rows": [dict(name=r[0], a=res["a"][r[1]], k3=res["k3"][r[1]], k1=res["k1"][r[1]], pct=len(r) > 2) for r in rows],
      "note": "同一套尺子:双层率=修正版 layer2F;边界回路越少=洞越少(外缘也算一个回路);A 做过去碎片+Taubin×10,KIRI 链照抄 README 不做。"}
json.dump(st, open("/root/page_cmp/stats_kiri.json", "w"), ensure_ascii=False, indent=1)
json.dump(res, open("/root/tsdf_improve/kiri/measure_kiri.json", "w"), ensure_ascii=False, indent=1); print("stats written")
