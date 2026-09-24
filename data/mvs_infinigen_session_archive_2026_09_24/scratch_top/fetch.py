import json,subprocess,sys,os,re
repos=["TQTQliu/ET-MVSNet","JianfeiJ/MVSMamba","FangjinhuaWang/IterMVS","JeffWang987/MVSTER","cvg/diffmvs","nianticlabs/mvsanywhere","whoiszzj/APD-MVS"]
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True,timeout=90).stdout
for r in repos:
    ok=False
    for br in ["main","master"]:
        t=sh(f'curl -sS -m 60 "https://api.github.com/repos/{r}/git/trees/{br}?recursive=1"')
        try: d=json.loads(t)
        except: continue
        if "tree" in d: ok=True; break
    if not ok: print(f"### {r}: TREE FETCH FAILED"); continue
    files=[e["path"] for e in d["tree"] if e["type"]=="blob"]
    cand=[f for f in files if re.search(r'(dataset|data_?loader|datasets/)',f,re.I) and f.endswith((".py",".yaml",".json",".yml"))]
    print(f"### {r}  ({len(files)} files, branch {br})")
    for c in cand[:14]: print("    ",c)
    os.makedirs(f"api/{r.replace('/','_')}",exist_ok=True)
    for c in cand[:14]:
        o=f"api/{r.replace('/','_')}/{c.replace('/','__')}"
        sh(f'curl -sS -m 60 -o "{o}" "https://raw.githubusercontent.com/{r}/{br}/{c}"')
