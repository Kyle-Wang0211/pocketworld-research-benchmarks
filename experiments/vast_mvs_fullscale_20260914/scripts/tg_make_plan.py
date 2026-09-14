import json, collections, os
d = json.load(open("/root/tg_meta.json"))
PER_ENV = int(os.environ.get("PER_ENV", "5"))
envs = collections.defaultdict(lambda: collections.defaultdict(set))
for f in d["siblings"]:
    p = f.get("rfilename", ""); parts = p.split("/")
    if len(parts) < 4: continue
    envs[parts[0]][parts[1]].add(parts[2])
plan = []
for e in sorted(envs):
    picked = []
    for ver in ("Data_omni", "Data_diff", "Data_anymal"):     # 偏好顺序:omni 覆盖最广
        for t in sorted(envs[e].get(ver, [])):
            if len(picked) >= PER_ENV: break
            picked.append((e, ver, t))
        if len(picked) >= PER_ENV: break
    plan += picked
print("环境数 %d  计划轨迹 %d" % (len(envs), len(plan)))
print("预估:每轨迹 150 帧 × 1.95 MB = 293 MB ⇒ 合计 %.1f GB,%s 组" % (len(plan)*0.293, f"{len(plan)*150:,}"))
with open("/root/tg_plan.tsv", "w") as f:
    for e, v, t in plan: f.write("%s\t%s\t%s\n" % (e, v, t))
# 切成 8 份并行
N = 8
for i in range(N):
    with open("/root/tg_plan_%d.tsv" % i, "w") as f:
        for j, (e, v, t) in enumerate(plan):
            if j % N == i: f.write("%s\t%s\t%s\n" % (e, v, t))
print("已切成 %d 份" % N)
