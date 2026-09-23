import sys
# mkdev.py <K_csv> <out_yaml>  —— A 臂的常量 K = CSV 第一行(= 第 0 帧的 ARKit K)
kcsv, out = sys.argv[1], sys.argv[2]
src = open("/Users/kaidongwang/Developer/viobench-recordings/_sweep_c_4ad6e500/dev_td+8_ba0.yaml").read()
for ln in open(kcsv):
    if ln.startswith('#') or not ln.strip():
        continue
    f = ln.strip().split(',')
    fx, fy, cx, cy = (float(x) for x in f[1:5])
    break
old = "intrinsics: [1279.01953125, 1279.01953125, 957.751708984375, 719.0894775390625]"
assert old in src
s = src.replace(old, f"intrinsics: [{fx!r}, {fy!r}, {cx!r}, {cy!r}]")
open(out, "w").write(s)
print(f"{out}: 冻第0帧 K = {fx} {fy} {cx} {cy}")
