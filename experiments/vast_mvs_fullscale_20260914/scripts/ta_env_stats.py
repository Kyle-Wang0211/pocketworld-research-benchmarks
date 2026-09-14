import os, glob, collections, re
ROOT = "/root/monotrain"
env = collections.defaultdict(lambda: [0, 0, None])
for d in sorted(os.listdir(ROOT)):
    if not d.startswith("ta_"): continue
    e = re.sub(r"_(easy|hard)_P\d+$", "", d[3:])
    p = f"{ROOT}/{d}/cams/pair.txt"
    n = int(open(p).readline()) if os.path.exists(p) else 0
    env[e][0] += 1; env[e][1] += n
    if env[e][2] is None:
        g = sorted(glob.glob(f"{ROOT}/{d}/blended_images/*.jpg"))
        if g: env[e][2] = g[len(g)//2]
tot = sum(v[1] for v in env.values())
print("%-26s %5s %9s %7s" % ("env", "traj", "tuples", "pctTA"))
for e, (s, n, img) in sorted(env.items(), key=lambda kv: -kv[1][1]):
    print("%-26s %5d %9s %6.1f%%" % (e, s, f"{n:,}", 100.0*n/tot))
print("%-26s %5d %9s" % ("TOTAL", sum(v[0] for v in env.values()), f"{tot:,}"))
with open("/root/ta_env_samples.txt", "w") as f:
    for e, (s, n, img) in sorted(env.items()):
        if img: f.write(e + "\t" + img + "\n")
print("\nsamples ->", len(env), "envs")
