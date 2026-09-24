#!/usr/bin/python3
"""Run gpu_vs_phone over every step1 capture that has a DB and photos. Per capture: stat for dataless, COPY the DB into
fixD/tmpdb, feed task lines (jpeg, db-copy, image_id, max_features), delete the copy. Output: fixD/out/gvp90.txt"""
import csv, os, subprocess, json, shutil, sqlite3, re, sys
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
F=SP+'/fixD'; OUT=F+'/out/gvp90.txt'
def ok(p):
    r=subprocess.run(['/usr/bin/stat','-f','%Sf',p],capture_output=True,text=True)
    return r.returncode==0 and 'dataless' not in r.stdout
def free_gib():
    s=os.statvfs('/private/tmp'); return s.f_bavail*s.f_frsize/2**30
rows=list(csv.DictReader(open(SP+'/step1/results.tsv'),delimiter='\t'))
done=set()
if os.path.exists(OUT):
    for l in open(OUT): done.add(l.split()[0].rsplit(':',1)[0])
os.makedirs(F+'/tmpdb',exist_ok=True)
for r in rows:
    cap=r['cap_id']; d=r['dir']
    if cap in done: continue
    if free_gib()<2.2: print('STOP disk',free_gib(),file=sys.stderr); break
    db=d+'/official_sfm_live.db'; fed=d+'/official_sfm_fed_frames.jsonl'
    if not (ok(db) and os.path.isdir(d+'/photos_highres') and ok(fed)): continue
    tmp=F+'/tmpdb/'+cap+'.db'; shutil.copyfile(db,tmp)
    con=sqlite3.connect(f'file:{tmp}?immutable=1',uri=True)
    imgs=con.execute('select image_id,name from images').fetchall()
    maxn=max([n for (n,) in con.execute('select rows from keypoints')] or [0]); con.close()
    jp={}
    for l in open(fed):
        try: j=json.loads(l)
        except: continue
        jp[j['frameId']]=os.path.basename(j['jpegPath'])
    tasks=[]
    for iid,name in imgs:
        m=re.search(r'(\d+)',name or '')
        if not m: continue
        fid=int(m.group(1)); b=jp.get(fid)
        if not b: continue
        p=d+'/photos_highres/'+b
        if os.path.exists(p) and ok(p): tasks.append(f'{p} {tmp} {iid} {maxf} {cap}:{fid}'.replace('{maxf}',str(maxn)) if False else f'{p} {tmp} {iid} {maxn} {cap}:{fid}')
    if tasks:
        res=subprocess.run([F+'/build/gpu_vs_phone'],input='\n'.join(tasks)+'\n',capture_output=True,text=True,env={'HOME':F+'/home','PATH':'/usr/bin:/bin'})
        open(OUT,'a').write(res.stdout)
        print(cap,len(tasks),'done',file=sys.stderr)
    os.remove(tmp)
