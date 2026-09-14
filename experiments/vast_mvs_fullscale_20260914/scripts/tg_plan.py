import json, collections, re
d = json.load(open("/root/tg_meta.json"))
print("LICENSE:", d.get("cardData", {}).get("license"), "| tags:", d.get("tags", [])[:6])
sib = d.get("siblings", [])
print("总文件数:", len(sib))
envs = collections.defaultdict(lambda: collections.defaultdict(set))
for f in sib:
    p = f.get("rfilename", "")
    parts = p.split("/")
    if len(parts) < 4: continue
    env, ver, traj, fn = parts[0], parts[1], parts[2], parts[-1]
    envs[env][ver].add(traj)
print("环境数:", len(envs))
tot_traj = 0
print("\n%-30s %-28s %s" % ("env", "versions", "trajs"))
for e in sorted(envs):
    vs = envs[e]
    n = sum(len(t) for t in vs.values()); tot_traj += n
    print("%-30s %-28s %d" % (e, ",".join(f"{k}:{len(v)}" for k, v in sorted(vs.items())), n))
print("\n轨迹总数:", tot_traj)
