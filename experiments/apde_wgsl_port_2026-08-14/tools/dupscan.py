import re, sys, glob, os
def norm_lines(path):
    txt = open(path, errors='ignore').read()
    txt = re.sub(r'/\*.*?\*/', '', txt, flags=re.S)
    txt = re.sub(r'//.*', '', txt)
    out = []
    for i, ln in enumerate(txt.split('\n'), 1):
        s = re.sub(r'\s+', '', ln)
        if len(s) >= 12:            # 忽略太短的行(括号/单赋值)
            out.append((i, s, ln.strip()))
    return out
def load(pats):
    d = {}
    for p in pats:
        for f in glob.glob(p):
            d[f] = norm_lines(f)
    return d
A = load(['gipuma/*.cu','gipuma/*.h','gipuma/*.cpp'])
B = load([sys.argv[1]+'/*.cu', sys.argv[1]+'/*.h', sys.argv[1]+'/*.cpp'])
gset = {}
for f, ls in A.items():
    for i, s, raw in ls:
        gset.setdefault(s, []).append((f, i, raw))
# 找连续 >=4 行的公共块
for f, ls in B.items():
    run = []
    for i, s, raw in ls:
        if s in gset:
            run.append((i, s, raw))
        else:
            if len(run) >= 4:
                src = gset[run[0][1]][0]
                print(f"\n── {f}:{run[0][0]}–{run[-1][0]}  ({len(run)} 行)  ← {src[0]}:{src[1]}")
                for _, _, r in run[:12]:
                    print("   ", r)
                if len(run) > 12: print(f"    …还有 {len(run)-12} 行")
            run = []
    if len(run) >= 4:
        src = gset[run[0][1]][0]
        print(f"\n── {f}:{run[0][0]}–{run[-1][0]}  ({len(run)} 行)  ← {src[0]}:{src[1]}")
        for _, _, r in run[:12]: print("   ", r)
tot = sum(1 for f,ls in B.items() for i,s,r in ls if s in gset)
alll = sum(len(ls) for ls in B.values())
print(f"\n>>> {sys.argv[1]}: 与 gipuma 逐行完全相同(去空白/注释)的行 {tot}/{alll} = {100*tot/max(alll,1):.1f}%")
