import numpy as np
def read_ply(p):
    with open(p, "rb") as f:
        hdr = b""
        while not hdr.endswith(b"end_header\n"):
            hdr += f.read(1)
        n = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.frombuffer(f.read(), count=n, dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    return rec
a = read_ply("ply_GT16K.ply")      # 上一轮全量导出(取色"成功")
b = read_ply("ply_GT16Kf3.ply")    # 本轮过滤导出
# 用坐标做键,比对同一点的颜色是否一致
ka = {(round(float(r["x"]),4), round(float(r["y"]),4), round(float(r["z"]),4)): (r["r"],r["g"],r["b"]) for r in a}
same = diff = miss = 0
for r in b[::37]:   # 抽样
    k = (round(float(r["x"]),4), round(float(r["y"]),4), round(float(r["z"]),4))
    if k in ka:
        if ka[k] == (r["r"],r["g"],r["b"]): same += 1
        else: diff += 1
    else: miss += 1
print(f"抽样 {same+diff+miss}: 颜色一致 {same} 不一致 {diff} 坐标未命中 {miss}")
print(f"均值RGB 全量 {a['r'].mean():.1f}/{a['g'].mean():.1f}/{a['b'].mean():.1f}  过滤 {b['r'].mean():.1f}/{b['g'].mean():.1f}/{b['b'].mean():.1f}")
