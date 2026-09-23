import subprocess,json,re,sys
def fetch(path):
    u="https://developer.apple.com/tutorials/data/documentation/"+path+".json"
    r=subprocess.run(["curl","-sL","-A","Mozilla/5.0 Chrome/120",u],capture_output=True,text=True,timeout=90).stdout
    try: return json.loads(r)
    except Exception: return None
def walk(o,out):
    if isinstance(o,dict):
        if o.get("type")=="text" and "text" in o: out.append(o["text"])
        elif o.get("type")=="codeVoice" and "code" in o: out.append("`"+o["code"]+"`")
        elif o.get("type")=="reference" and "title" in o: out.append(o["title"])
        for v in o.values(): walk(v,out)
    elif isinstance(o,list):
        for v in o: walk(v,out)
def text(path):
    d=fetch(path)
    if d is None: return None
    out=[]; walk(d,out)
    return " ".join(out)
def grep(t,kws,ctx=300):
    seen=set()
    for kw in kws:
        for m in re.finditer(kw,t,flags=re.I):
            s=t[max(0,m.start()-ctx):m.start()+ctx]
            k=s[:60]
            if k in seen: continue
            seen.add(k); print("  *",s,"\n  ---")
if __name__=="__main__":
    path=sys.argv[1]; kws=sys.argv[2:]
    t=text(path)
    if t is None: print("FAILED",path); sys.exit(1)
    print("=====",path,len(t))
    open(re.sub(r'\W+','_',path)+'.txt','w').write(t)
    grep(t,kws)
