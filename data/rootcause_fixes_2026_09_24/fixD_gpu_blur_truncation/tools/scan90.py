#!/usr/bin/python3
"""Scan all 90 step1 captures (read-only; stat for 'dataless' before opening; DB COPIED into fixD/tmpdb and the copy opened immutable; copy deleted after).
Per frame: DB keypoint stats (n, scale median, frac<3px, empty 256px tiles) + GPU timestamp pass durations."""
import csv, os, subprocess, json, sqlite3, sys
import numpy as np
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
OUT=SP+'/fixD/out/scan90.jsonl'
def ok(p):
    r=subprocess.run(['/usr/bin/stat','-f','%Sf',p],capture_output=True,text=True)
    return r.returncode==0 and 'dataless' not in r.stdout
rows=list(csv.DictReader(open(SP+'/step1/results.tsv'),delimiter='\t'))
fo=open(OUT,'w')
for r in rows:
    d=r['dir']; cap=r['cap_id']; db=d+'/official_sfm_live.db'
    rec={'cap':cap,'build':r['build_stamp'],'date':r['date_utc']}
    if not ok(db):
        rec['db']='missing_or_dataless'; fo.write(json.dumps(rec)+'\n'); continue
    import shutil
    tmp=SP+'/fixD/tmpdb/'+cap+'.db'; os.makedirs(SP+'/fixD/tmpdb',exist_ok=True)
    shutil.copyfile(db,tmp)   # work on a COPY (task rule); original never opened by sqlite
    con=sqlite3.connect(f'file:{tmp}?immutable=1',uri=True)
    try:
        imgs=dict(con.execute('select image_id,name from images'))
        cams={i:(w,h) for i,w,h in con.execute('select camera_id,width,height from cameras')}
        imcam=dict(con.execute('select image_id,camera_id from images'))
        frames=[]
        for iid,rws,cols,blob in con.execute('select image_id,rows,cols,data from keypoints'):
            if not rws: frames.append({'iid':iid,'n':0}); continue
            a=np.frombuffer(blob,np.float32).reshape(rws,cols)
            if cols==6:
                sx=np.sqrt(a[:,2]**2+a[:,4]**2); sy=np.sqrt(a[:,3]**2+a[:,5]**2); s=0.5*(sx+sy)
            elif cols==4: s=a[:,2]
            else: s=np.full(rws,np.nan)
            W,H=cams.get(imcam.get(iid),(4032,3024))
            T=256; ny,nx=(H+T-1)//T,(W+T-1)//T
            h,_,_=np.histogram2d(a[:,1],a[:,0],bins=[ny,nx],range=[[0,ny*T],[0,nx*T]])
            # largest empty axis-aligned run of tile COLUMNS (right-side dead block proxy)
            colocc=(h>0).sum(0)
            frames.append({'iid':iid,'name':imgs.get(iid),'n':int(rws),'W':W,'H':H,
                           's_med':float(np.nanmedian(s)),'f_lt3':float(np.mean(s<3.0)),
                           'empty_tiles':float((h==0).mean()),
                           'x_med_rel':float(np.median(a[:,0])/W),
                           'cols_empty':int((colocc==0).sum())})
        rec['frames']=frames
    except Exception as e:
        rec['db_err']=str(e)
    try: con.close(); os.remove(tmp)
    except Exception: pass
    mf=d+'/sfm_match_fail.jsonl'; ts={}
    if os.path.exists(mf) and ok(mf):
        for l in open(mf):
            if '"gpu_timestamp_frame_v1"' not in l: continue
            try: g=json.loads(l)
            except: continue
            if g.get('valid')==1:
                ts[g['frame_id']]=[round((b-a)/1e6,3) for a,b,st in g['raw_pairs'] if st==0]
    rec['ts_pyr']=ts
    fo.write(json.dumps(rec)+'\n'); fo.flush()
    print(cap, len(rec.get('frames',[])), 'ts', len(ts), file=sys.stderr)
