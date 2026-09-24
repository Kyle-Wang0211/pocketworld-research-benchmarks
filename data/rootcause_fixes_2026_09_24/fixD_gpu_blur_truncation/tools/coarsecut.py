#!/usr/bin/python3
"""DB-only fingerprint of a prefix-truncated octave-0 blur dispatch: along x (strip order of the fused kernel) find the
boundary b after which coarse keypoints (scale>=S_COARSE) vanish while fine keypoints (scale<S_FINE) persist.
Reads a COPY of each DB (copied into fixD/tmpdb, deleted after)."""
import csv, os, subprocess, json, sqlite3, shutil, sys
import numpy as np
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
S_COARSE, S_FINE = 8.0, 3.2
def ok(p):
    r=subprocess.run(['/usr/bin/stat','-f','%Sf',p],capture_output=True,text=True)
    return r.returncode==0 and 'dataless' not in r.stdout
out=open(SP+'/fixD/out/coarsecut.jsonl','w')
for r in csv.DictReader(open(SP+'/step1/results.tsv'),delimiter='\t'):
    db=r['dir']+'/official_sfm_live.db'
    if not ok(db): continue
    tmp=SP+'/fixD/tmpdb/cc.db'; shutil.copyfile(db,tmp)
    con=sqlite3.connect(f'file:{tmp}?immutable=1',uri=True)
    names=dict(con.execute('select image_id,name from images'))
    for iid,rows,cols,blob in con.execute('select image_id,rows,cols,data from keypoints'):
        if not rows or cols!=6: continue
        a=np.frombuffer(blob,np.float32).reshape(rows,cols)
        s=0.5*(np.hypot(a[:,2],a[:,4])+np.hypot(a[:,3],a[:,5]))
        if np.all(np.abs(s-1)<1e-6): continue   # unit-affine era (no persisted scale)
        x=a[:,0]; W=4032.0
        co=x[s>=S_COARSE]; fi=x[s<S_FINE]
        if len(co)<50 or len(fi)<50: continue
        best=(0.0,None)
        for b in np.arange(0.2,0.8,0.02)*W:
            c_after=np.mean(co>=b); f_after=np.mean(fi>=b)
            if c_after<=0.01:
                score=f_after
                if score>best[0]: best=(score,float(b))
        fid=int(''.join(ch for ch in (names.get(iid) or '') if ch.isdigit()) or -1)
        out.write(json.dumps({'cap':r['cap_id'],'fid':fid,'n':int(rows),'fine_after_cut':round(best[0],3),'cut_x':best[1]})+'\n')
    con.close(); os.remove(tmp)
