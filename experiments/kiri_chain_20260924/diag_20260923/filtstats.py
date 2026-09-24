"""Where do region pixels die in the official gate? Replays filter.py (imported) per view, decomposes by region."""
import numpy as np, json, cv2, sys, csv
from replay_lib import *
L=np.load(sys.argv[1] if len(sys.argv)>1 else "labels.npz")["labels"]; TAG=sys.argv[2] if len(sys.argv)>2 else ""
R=json.load(open("regions_planes.json")); planes={1:(np.array(R["wall"]["n"]),R["wall"]["d"]),2:(np.array(R["floor"]["n"]),R["floor"]["d"]),4:(np.array(R["white"]["n"]),R["white"]["d"])}
uu,vv=np.meshgrid(np.arange(768)+0.0,np.arange(576)+0.0)
ALT={"ours(3,1px)":(3,1.0),"testpy_default(2,1px)":(2,1.0),"README_general(2,0.125px)":(2,0.125),"eth3d_like(1,0.5px)":(1,0.5),"eth3d_like(1,1px)":(1,1.0),"eth3d_like(1,2px)":(1,2.0)}
names=["wall","floor","suitcase","white"]
agg={n:{} for n in names}
def add(r,key,val): agg[r][key]=agg[r].get(key,0)+val
rows=[]
for rv,sv in PAIR_DATA:
    o=replay(rv,sv,extra=True)
    lab=L[rv]; d=o["d"]; rng=(d>o["dmin"])&(d<o["dmax"])
    # self-check: our re-thresholded gsum at (1px,1%) must equal the imported gsum
    g_re=sum(((dd<1.0)&(rr<0.01)&rng).astype(np.int32) for dd,rr in zip(o["dists"],o["rels"]))
    assert np.array_equal(g_re,o["gsum"]), "rethreshold mismatch"
    gray=cv2.cvtColor(cv2.imread(f"{OF}/images/{rv:08d}.jpg"),cv2.COLOR_BGR2GRAY).astype(np.float32)/255
    tex=np.sqrt(np.clip(cv2.blur(gray*gray,(11,11))-cv2.blur(gray,(11,11))**2,0,None))
    K,E=o["K"].astype(np.float64),o["E"].astype(np.float64); Rw=E[:3,:3]; C=-Rw.T@E[:3,3]
    rw=(Rw.T@(np.linalg.inv(K)@np.stack([uu.ravel(),vv.ravel(),np.ones(uu.size)]))).T
    for ci,rn in enumerate(names,1):
        m=lab==ci; N=int(m.sum())
        if N==0: continue
        ph=o["photo"][m]; gs=o["gsum"][m]; fin=o["final"][m]
        add(rn,"N",N); add(rn,"final",int(fin.sum()))
        add(rn,"photo_fail",int((~ph).sum())); add(rn,"geo_fail",int((gs<3).sum()))
        add(rn,"only_photo",int((~ph&(gs>=3)).sum())); add(rn,"only_geo",int((ph&(gs<3)).sum())); add(rn,"both",int((~ph&(gs<3)).sum()))
        for s in range(3): add(rn,f"c{s}_fail",int((~o["pm"][s][m]).sum()))
        h=np.bincount(gs,minlength=11); agg[rn]["gsum_hist"]=agg[rn].get("gsum_hist",np.zeros(11,np.int64))+h
        add(rn,"tex_sum",float(tex[m].sum())); agg[rn].setdefault("tex_samples",[]).append(tex[m][::50])
        for an,(mt,px) in ALT.items():
            g=sum(((dd<px)&(rr<0.01)&rng).astype(np.int32) for dd,rr in zip(o["dists"],o["rels"]))
            add(rn,"alt_"+an,int((o["photo"]&(g>=mt))[m].sum()))
        row=dict(view=rv,region=rn,N=N,final=int(fin.sum()),photo_fail=int((~ph).sum()),geo_fail_gsum_lt3=int((gs<3).sum()),only_photo=int((~ph&(gs>=3)).sum()),only_geo=int((ph&(gs<3)).sum()),both=int((~ph&(gs<3)).sum()))
        if ci in planes:
            n,dd=planes[ci]; z=(-(n@C+dd)/(rw@n)).reshape(576,768)[m]
            err=np.abs(d[m]-z)/z; acc=err<0.01
            add(rn,"acc1",int(acc.sum())); add(rn,"acc2",int((err<0.02).sum())); add(rn,"acc5",int((err<0.05).sum()))
            add(rn,"acc_and_final",int((acc&fin).sum())); add(rn,"inacc_and_final",int((~acc&fin).sum()))
            add(rn,"acc_killed_photo",int((acc&~ph).sum())); add(rn,"acc_killed_geo_only",int((acc&ph&(gs<3)).sum()))
            # accuracy of what survives (averaged depth vs plane)
            e2=np.abs(o["davg"][m]-z)/z; add(rn,"final_err_lt1",int((fin&(e2<0.01)).sum()))
            agg[rn].setdefault("err_samples",[]).append(err[::20]); agg[rn].setdefault("errf_samples",[]).append(e2[fin][::20])
            row.update(raw_acc1pct=int(acc.sum()))
        rows.append(row)
with open(f"filt_per_view{TAG}.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())+["raw_acc1pct"]); w.writeheader(); [w.writerow(r) for r in rows]
out={}
for rn in names:
    a=agg[rn]; N=a["N"]; o={k:(v/N if isinstance(v,(int,float)) and k not in("N","tex_sum") else v) for k,v in a.items() if not k.endswith("samples") and k!="gsum_hist"}
    o["N"]=N; o["tex_mean"]=a["tex_sum"]/N; ts=np.concatenate(a["tex_samples"]); o["tex_p50"]=float(np.median(ts)); o["tex_p90"]=float(np.percentile(ts,90))
    o["gsum_hist_frac"]=(a["gsum_hist"]/N).round(4).tolist()
    if "err_samples" in a:
        es=np.concatenate(a["err_samples"]); o["raw_relerr_p50_p75_p90"]=np.percentile(es,[50,75,90]).round(4).tolist()
        ef=np.concatenate(a["errf_samples"]); o["final_relerr_p50_p90"]=np.percentile(ef,[50,90]).round(4).tolist() if len(ef) else None
    out[rn]=o
json.dump(out,open(f"filt_summary{TAG}.json","w"),indent=1)
for rn in names:
    print("=====",rn); [print(f"  {k}: {v}") for k,v in out[rn].items()]
