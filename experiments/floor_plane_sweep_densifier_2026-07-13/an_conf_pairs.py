#!/usr/bin/env python3
"""Lever2 (conf yield stratified) + Lever3 (unmatched floor-pair headroom). Analysis only."""
import json, numpy as np, cv2, itertools
import fr_common as fc
FR = fc.FR
M = np.load(FR + "/fr_matches.npz")
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")}, key=lambda s: tuple(map(int, s.split("_"))))
HAS = hasattr(cv2, "USAC_MAGSAC"); RANSAC = cv2.USAC_MAGSAC if HAS else cv2.FM_RANSAC
FB = fc.FLOOR_BAND

def tri2(i,j,x0,y0,x1,y1):
    P0=fc.projmat(i); P1=fc.projmat(j)
    A=np.array([x0*P0[2]-P0[0], y0*P0[2]-P0[1], x1*P1[2]-P1[0], y1*P1[2]-P1[1]])
    _,_,Vt=np.linalg.svd(A); X=Vt[-1]; return X[:3]/X[3]

# ---- Lever2: per-match 2-view floor yield stratified by conf ----
bands=[(0.20,0.25),(0.25,0.30),(0.30,0.40),(0.40,0.60),(0.60,1.01)]
n_match=np.zeros(len(bands)); n_pass=np.zeros(len(bands)); n_floor=np.zeros(len(bands))
for p in pairs:
    i,j=map(int,p.split("_"))
    p0=M[f"{p}_p0"].astype(np.float64); p1=M[f"{p}_p1"].astype(np.float64); cf=M[f"{p}_conf"]
    if len(p0)<8: continue
    Fm,mask=cv2.findFundamentalMat(p0,p1,RANSAC,fc.MAGSAC_T,0.999,200000)
    mask=np.ones(len(p0),bool) if mask is None else mask.ravel().astype(bool)
    samp=fc.sampson(fc.F_arkit(i,j),p0,p1); keep=mask&(samp<fc.SAMPSON_T)
    # per band
    for bi,(lo,hi) in enumerate(bands):
        sel=(cf>=lo)&(cf<hi); n_match[bi]+=sel.sum(); ks=sel&keep; n_pass[bi]+=ks.sum()
    # floor yield: triangulate kept matches at this pair
    ci=fc.C_of(i); cj=fc.C_of(j)
    for idx in np.where(keep)[0]:
        X=tri2(i,j,p0[idx,0],p0[idx,1],p1[idx,0],p1[idx,1])
        oki=(fc.R_of(i)@X+fc.t_of(i))[2]; okj=(fc.R_of(j)@X+fc.t_of(j))[2]
        if not(fc.DEPTH_MIN<oki<fc.DEPTH_MAX and fc.DEPTH_MIN<okj<fc.DEPTH_MAX): continue
        # reproj
        for fid,xx,yy in [(i,p0[idx,0],p0[idx,1]),(j,p1[idx,0],p1[idx,1])]:
            uv=fc.K_of(fid)@(fc.R_of(fid)@X+fc.t_of(fid)); uv=uv[:2]/uv[2]
            if np.hypot(uv[0]-xx,uv[1]-yy)>fc.REPROJ_T: break
        else:
            d0=X-ci; d1=X-cj; ang=np.degrees(np.arccos(np.clip((d0/np.linalg.norm(d0))@(d1/np.linalg.norm(d1)),-1,1)))
            if ang>=fc.TRI_ANGLE_MIN and abs(fc.floor_dist(X))<FB:
                c=cf[idx]
                for bi,(lo,hi) in enumerate(bands):
                    if lo<=c<hi: n_floor[bi]+=1; break
print("=== Lever2: conf-band stratified (2-view per-match floor yield) ===")
print("band        n_match   F+S_pass%   floor_pts   floor_yield_per_match")
for bi,(lo,hi) in enumerate(bands):
    ym=n_floor[bi]/n_match[bi] if n_match[bi] else 0
    print("[%.2f,%.2f) %8d   %6.1f%%   %6d      %.4f%%"%(lo,hi,n_match[bi],100*n_pass[bi]/max(1,n_match[bi]),n_floor[bi],100*ym))
print("total floor(2view proxy):",int(n_floor.sum()))

# ---- Lever3: unmatched floor-floor pair headroom ----
ff=json.load(open(FR+"/floor_frame_ids.json"))["floor_frame_ids"]
matched=set(tuple(sorted(map(int,p.split("_")))) for p in pairs)
def floor_parallax(i,j):
    # parallax at floor centroid: angle between rays from Ci,Cj to floor centroid
    fc_cen=np.array(json.load(open(FR+"/production_floor_stats.json"))["floor_centroid_world"])
    d0=fc_cen-fc.C_of(i); d1=fc_cen-fc.C_of(j)
    return np.degrees(np.arccos(np.clip((d0/np.linalg.norm(d0))@(d1/np.linalg.norm(d1)),-1,1)))
def sees_floor(i):
    # camera looks toward floor: view_dir has downward component along plane normal, and centroid in front
    fc_cen=np.array(json.load(open(FR+"/production_floor_stats.json"))["floor_centroid_world"])
    Xc=fc.R_of(i)@fc_cen+fc.t_of(i);
    if Xc[2]<=0: return False
    uv=fc.K_of(i)@Xc; uv=uv[:2]/uv[2]
    return -200<uv[0]<fc.WORK_W+200 and -200<uv[1]<fc.WORK_H+200
allpairs=list(itertools.combinations(sorted(map(int,ff)),2))
viable=[]; already=0
for i,j in allpairs:
    par=floor_parallax(i,j); base=np.linalg.norm(fc.C_of(i)-fc.C_of(j))
    good = (2.0<=par<=25.0) and (base<=1.2) and sees_floor(i) and sees_floor(j)
    if (i,j) in matched:
        already+=1
    elif good:
        viable.append((i,j,par,base))
print("\n=== Lever3: floor-floor pair headroom ===")
print("floor frames=%d  total possible pairs=%d  matched=%d"%(len(ff),len(allpairs),len(matched)))
print("matched that are 'good' by criteria:",already,"(of 306)")
print("UNMATCHED viable pairs (parallax2-25,base<1.2m,both see floor centroid):",len(viable))
pars=np.array([v[2] for v in viable])
if len(viable): print("  their floor parallax: median=%.1f p25=%.1f p75=%.1f"%(np.median(pars),np.percentile(pars,25),np.percentile(pars,75)))
print("=== DONE")
