# Oracle 上界: 先验=法医真值平面(measure_wall P16k 稳健拟合), score=|d_MVS - d_plane|
# 任何"平面先验+阈值门"路线的可分性天花板(覆盖率=1, 无 Delaunay 误差)
import numpy as np, json
from scipy.stats import rankdata
OUT="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/da3probe"
FRAMES=[78,79,80,81,82,83,85,86,87,100,103,107,125]
CM=42.0; TAUS=[1.0,2.0,3.0,3.5,4.0,4.5,5.0,6.0,8.0]
def auc(pos,neg):
    sc=np.concatenate([pos,neg]); rk=rankdata(sc); n1,n0=len(pos),len(neg)
    return float((rk[:n1].sum()-n1*(n1+1)/2)/(n1*n0))
res={}; wp={t:dict(det=0,tb=0,kill=0,tc=0) for t in TAUS}
aucs=[]; aucs_s=[]
for fr in FRAMES:
    P=np.load(f"{OUT}/frame_{fr}.npz")
    bM=P["depth_mvs"].astype(np.float64); aP=P["depth_plane"].astype(np.float64)
    loc=P["blob_loc"]; clean=P["clean"]; neg=np.nonzero(clean)[0]
    s_ab=np.abs(bM-aP); s_sg=bM-aP
    pos_a,neg_a=s_ab[loc],s_ab[neg]; pos_s,neg_s=s_sg[loc],s_sg[neg]
    A=auc(pos_a,neg_a); AS=auc(pos_s,neg_s)
    res[fr]=dict(auc_abs=round(A,4),auc_signed=round(AS,4),
                 clean_sgn_med_cm=round(float(np.median(neg_s))*CM,2),
                 blob_sgn_med_cm=round(float(np.median(pos_s))*CM,2))
    aucs.append(A); aucs_s.append(AS)
    for t in TAUS:
        th=t/CM
        wp[t]["det"]+=int((pos_s>th).sum()); wp[t]["tb"]+=len(loc)
        wp[t]["kill"]+=int((neg_s>th).sum()); wp[t]["tc"]+=len(neg)
    print(fr,res[fr],flush=True)
print("oracle abs AUC med/min/max",round(float(np.median(aucs)),4),round(min(aucs),4),round(max(aucs),4))
print("oracle signed AUC med/min/max",round(float(np.median(aucs_s)),4),round(min(aucs_s),4),round(max(aucs_s),4))
tbl=[dict(tau_cm=t,recall=round(wp[t]["det"]/wp[t]["tb"],4),kill=round(wp[t]["kill"]/wp[t]["tc"],4)) for t in TAUS]
for w in tbl: print(w)
json.dump(dict(per_frame={str(k):v for k,v in res.items()},
               med_abs=round(float(np.median(aucs)),4),med_signed=round(float(np.median(aucs_s)),4),
               working_points_signed=tbl),
          open("/Users/kaidongwang/Documents/progecttwo/_artifacts/delaunay_prior_20260818/oracle_plane_bound.json","w"),indent=1)
