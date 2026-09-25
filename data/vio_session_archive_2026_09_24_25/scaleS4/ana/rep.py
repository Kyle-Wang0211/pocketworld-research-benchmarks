import os, sys, re, subprocess, time, json, numpy as np
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
S4=SP+'/scaleS4'; RUNNER=S4+'/build-pc/pw_euroc_runner'; LOCK=SP+'/.xrslam_run.lock'
REC=os.path.expanduser('~/Developer/viobench-recordings/')
def load(p):
    T,P=[],[]
    for ln in open(p):
        f=ln.split()
        if len(f)<8 or ln.startswith('#'): continue
        T.append(float(f[0])); P.append([float(f[1]),float(f[2]),float(f[3])])
    T=np.array(T); 
    if T[0]>1e12: T=T*1e-9
    return T,np.array(P)
def umeyama(X,Y,ws=True):
    mx,my=X.mean(1,keepdims=True),Y.mean(1,keepdims=True); Xc,Yc=X-mx,Y-my
    S=Yc@Xc.T/X.shape[1]; U,D,Vt=np.linalg.svd(S); d=np.ones(3)
    if np.linalg.det(U)*np.linalg.det(Vt)<0: d[2]=-1
    R=U@np.diag(d)@Vt; s=(D*d).sum()/((Xc**2).sum()/X.shape[1]) if ws else 1.0
    return s,R,my-s*R@mx
def score(est, ref, tmax=None):
    te,Pe=load(est); tr,Pr=load(ref)
    if tmax is not None:
        k=te<=te[0]+tmax; te,Pe=te[k],Pe[k]
    idx=np.clip(np.searchsorted(tr,te),1,len(tr)-1); l=np.abs(te-tr[idx-1]); r=np.abs(te-tr[idx])
    pick=np.where(l<r,idx-1,idx); ok=np.minimum(l,r)<0.010
    X=Pe[ok].T; Y=Pr[pick[ok]].T
    s,R,t=umeyama(X,Y); e=np.linalg.norm((s*R@X+t)-Y,axis=0)
    s1,R1,t1=umeyama(X,Y,False); e1=np.linalg.norm((R1@X+t1)-Y,axis=0)
    # est/ref size ratio: est bigger => ratio>1
    return dict(pairs=int(ok.sum()), n_est=len(te), ratio_pct=(1/s-1)*100, sim3_cm=np.sqrt((e**2).mean())*100, se3_cm=np.sqrt((e1**2).mean())*100,
                t_first=te[0])
def lock():
    while True:
        try: os.mkdir(LOCK); return
        except FileExistsError: time.sleep(2)
def unlock():
    try: os.rmdir(LOCK)
    except FileNotFoundError: pass
def run(ds, slam, dev, tag, kcsv=None, ref=None, force=False, tmax=None, runner=None):
    tum=f'{S4}/runs/{tag}.tum'
    if force or not os.path.exists(tum):
        cmd=[globals()["RUNNER"], slam, dev, 'euroc://'+ds, tum]+(['--intrinsics-csv',kcsv] if kcsv else [])
        lock(); t0=time.time()
        try:
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=3600)
        finally: unlock()
        open(f'{S4}/runs/{tag}.log','w').write(r.stderr[-20000:])
        el=time.time()-t0
    else: el=0
    if not os.path.exists(tum) or os.path.getsize(tum)==0:
        print(f'{tag:40s} NO OUTPUT'); return None
    m=score(tum, ref, tmax) if ref else {}
    m['sec']=round(el,1); m['tag']=tag
    print(f"{tag:40s} pairs {m.get('pairs')}/{m.get('n_est')}  est/ref {m.get('ratio_pct',0):+6.2f}%  Sim3 {m.get('sim3_cm',0):5.2f}cm  SE3 {m.get('se3_cm',0):5.2f}cm  ({el:.0f}s)", flush=True)
    with open(f'{S4}/runs/results.jsonl','a') as f: f.write(json.dumps(m)+'\n')
    return m
def make_dev(src, dst, **kv):
    s=open(src).read()
    for k,v in kv.items():
        if k=='intrinsics':
            s,n=re.subn(r'^(\s*intrinsics:\s*)\[[^\]]*\]', lambda m: m.group(1)+'['+', '.join(repr(float(x)) for x in v)+']', s, count=1, flags=re.M)
        elif k=='resolution':
            s,n=re.subn(r'^(\s*resolution:\s*)\[[^\]]*\]', lambda m: m.group(1)+f'[{v[0]}, {v[1]}]', s, count=1, flags=re.M)
        elif k=='time_offset':
            s,n=re.subn(r'^(\s*time_offset:\s*)[-\d.eE+]+', lambda m: m.group(1)+repr(float(v)), s, count=1, flags=re.M)
        elif k=='q_bc':
            s,n=re.subn(r'^(\s*q_bc:\s*)\[[^\]]*\]', lambda m: m.group(1)+'['+', '.join(repr(float(x)) for x in v)+']', s, count=1, flags=re.M)
        elif k=='distortion':
            s,n=re.subn(r'^(\s*distortion:\s*)\[[^\]]*\]', lambda m: m.group(1)+'['+', '.join(repr(float(x)) for x in v)+']', s, count=1, flags=re.M)
        elif k=='distortion_flag':
            s,n=re.subn(r'^(\s*camera_distortion_flag:\s*)\d+', lambda m: m.group(1)+str(int(v)), s, count=1, flags=re.M)
        else: raise SystemExit('bad key '+k)
        if n!=1: raise SystemExit(f'key {k} not found once in {src}')
    open(dst,'w').write(s); return dst
