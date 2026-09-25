#!/usr/bin/env python3
"""dip13f: thumbnails at chosen recording times with the engine's landmarks overlaid.
green = mapped landmark reprojects <3 px at the loc solve; red = >=3 px; magenta x = track rejected by the
TT_VALID rpe gate in the window solve ending at that frame. Usage: thumbs.py <log.jsonl> <outdir> t1 t2 ..."""
import sys, json, numpy as np, cv2, os
RUN='/Users/kaidongwang/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935'
T0=254666.645033333
import os; TDSH=float(os.environ.get("TDSH","0"))
log, outdir = sys.argv[1], sys.argv[2]; times=[float(x) for x in sys.argv[3:]]
os.makedirs(outdir, exist_ok=True)
ev={'loc':[], 'win':[], 'ft':[]}
for l in open(log):
    d=json.loads(l)
    if d['ev'] in ev: ev[d['ev']].append(d)
off={}
for ln in open(RUN+'/frames.pwvi'):
    if ln.strip(): d=json.loads(ln); off[d['frame']]=d['offset']
rows=[l.strip().split(',') for l in open(RUN+'/camera_index.csv').readlines()[1:] if l.strip()]
ct=np.array([int(r[0])*1e-9 for r in rows]); cf=[int(r[1]) for r in rows]
mm=np.memmap(RUN+'/frames.bin',dtype=np.uint8,mode='r')
lt=np.array([d['t'] for d in ev['loc']]); wt=np.array([d['t'] for d in ev['win']]); ftt={round(d['t'],4):d for d in ev['ft']}
tiles=[]
for tq in times:
    i=int(np.argmin(np.abs(lt-(T0+tq+TDSH)))); L=ev["loc"][i]; t=L["t"]
    j=int(np.argmin(np.abs(ct-(t-TDSH)))); fr=cf[j]
    full=np.asarray(mm[off[fr]:off[fr]+1920*1440]).reshape(1440,1920)
    img=np.rint(full.reshape(480,3,640,3).astype(np.float64).mean(axis=(1,3))).astype(np.uint8)
    im=cv2.cvtColor(img,cv2.COLOR_GRAY2BGR)
    nin=nout=0
    for u,v,e,z,kn in L['pts']:
        c=(0,200,0) if e<3 else (0,0,255); nin+=e<3; nout+=e>=3
        cv2.circle(im,(int(round(u)),int(round(v))),4,c,2)
    k=np.where(np.abs(wt-t)<1e-4)[0]; nrej=0
    if len(k):
        for g in ev['win'][k[0]]['gate']:
            u,v,r,dok,val,kn,tl=g
            if not val and abs(tl-t)<1e-4:
                nrej+=1; x,y=int(round(u)),int(round(v))
                cv2.line(im,(x-4,y-4),(x+4,y+4),(255,0,255),2); cv2.line(im,(x-4,y+4),(x+4,y-4),(255,0,255),2)
    f=ftt.get(round(t,4),{})
    lab=f"t={t-TDSH-T0:5.2f}s fx={3*f.get('fx',0):.0f} trk={f.get('n_out','?')} map={len(L['pts'])} in<3px={nin} rej={nrej}"
    cv2.rectangle(im,(0,0),(640,22),(0,0,0),-1); cv2.putText(im,lab,(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1,cv2.LINE_AA)
    cv2.imwrite(f"{outdir}/t{tq:05.2f}.png",im); tiles.append(cv2.resize(im,(480,360)))
    print(lab)
cols=4; rows_=int(np.ceil(len(tiles)/cols))
while len(tiles)<rows_*cols: tiles.append(np.zeros_like(tiles[0]))
sheet=np.vstack([np.hstack(tiles[r*cols:(r+1)*cols]) for r in range(rows_)])
cv2.imwrite(f"{outdir}/contact_sheet.jpg",sheet,[cv2.IMWRITE_JPEG_QUALITY,85]); print('sheet',sheet.shape)
