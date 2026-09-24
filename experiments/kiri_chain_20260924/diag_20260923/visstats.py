"""Is gsum<3 on the wall a coverage problem (the 10 paired src views do not see the pixel) or a consistency problem
(they see it but the depths disagree)? True 3D point: plane point (wall/floor) or coarse-mesh hit (suitcase).
Visible in src = projects inside src image AND coarse mesh (12mm thr0) has no surface > M before it along the src ray."""
import numpy as np, open3d as o3d, json, sys
from replay_lib import *
L=np.load("labels4.npz")["labels"]
R=json.load(open("regions_planes.json")); planes={1:(np.array(R["wall"]["n"]),R["wall"]["d"]),2:(np.array(R["floor"]["n"]),R["floor"]["d"]),4:(np.array(R["white"]["n"]),R["white"]["d"])}
cm=o3d.io.read_triangle_mesh("coarse12_thr0.ply"); scn=o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(cm))
uu,vv=np.meshgrid(np.arange(768)+0.0,np.arange(576)+0.0); M=0.08
names={1:"wall",2:"floor",3:"suitcase",4:"white"}
S={n:dict(N=0,vis_hist=np.zeros(11,np.int64),cov_lt3=0,cov_ge3=0,cov_ge3_geofail=0,cov_ge3_pass=0,src_vis=0,src_vis_ok=0,src_vis_fail_px_only=0,src_vis_fail_rel_only=0,src_vis_fail_both=0,src_vis_fail_range=0,ref_acc_srcfail=0,ref_inacc_srcfail=0) for n in names.values()}
def cast(orig,dirs):
    r=scn.cast_rays(o3d.core.Tensor(np.concatenate([orig,dirs],1).astype(np.float32)))["t_hit"].numpy(); return r
for rv,sv in PAIR_DATA:
    o=replay(rv,sv,extra=True); lab=L[rv]
    K=o["K"].astype(np.float64); E=o["E"].astype(np.float64); Rw=E[:3,:3]; C=-Rw.T@E[:3,3]
    rw=(Rw.T@(np.linalg.inv(K)@np.stack([uu.ravel(),vv.ravel(),np.ones(uu.size)]))).T
    nrm=np.linalg.norm(rw,axis=1)
    for code,rn in names.items():
        m=(lab==code).ravel()
        if m.sum()==0: continue
        if code in planes:
            n,d=planes[code]; z=-(n@C+d)/(rw[m]@n); X=C+z[:,None]*rw[m]; zref=z
        else:
            th=cast(np.tile(C,(m.sum(),1)),rw[m]/nrm[m,None]); zref=th/nrm[m]; X=C+zref[:,None]*rw[m]
        dref=o["d"].ravel()[m]; refacc=np.abs(dref-zref)/zref<0.01
        rng=((o["d"]>o["dmin"])&(o["d"]<o["dmax"])).ravel()[m]
        vis_cnt=np.zeros(m.sum(),np.int32); gs=o["gsum"].ravel()[m]
        for j,s in enumerate(sv):
            Ks,Es,_,_=cam(s); Ks=Ks.astype(np.float64); Es=Es.astype(np.float64); Cs=-Es[:3,:3].T@Es[:3,3]
            Xc=(Es[:3,:3]@X.T).T+Es[:3,3]; zc=Xc[:,2]; uv=(Ks@Xc.T).T; us=uv[:,0]/uv[:,2]; vs=uv[:,1]/uv[:,2]
            inb=(zc>0)&(us>=0)&(us<=767)&(vs>=0)&(vs<=575)
            dvec=X-Cs; dist=np.linalg.norm(dvec,axis=1); th=np.full(len(X),np.inf)
            if inb.any(): th[inb]=cast(np.tile(Cs,(inb.sum(),1)),dvec[inb]/dist[inb,None])
            vis=inb&~(th<dist-M)
            vis_cnt+=vis
            dd=o["dists"][j].ravel()[m]; rr=o["rels"][j].ravel()[m]
            okpx=dd<1.0; okrel=rr<0.01; ok=okpx&okrel&rng
            st=S[rn]; st["src_vis"]+=int(vis.sum()); st["src_vis_ok"]+=int((vis&ok).sum())
            st["src_vis_fail_px_only"]+=int((vis&~okpx&okrel).sum()); st["src_vis_fail_rel_only"]+=int((vis&okpx&~okrel).sum()); st["src_vis_fail_both"]+=int((vis&~okpx&~okrel).sum())
            st["src_vis_fail_range"]+=int((vis&okpx&okrel&~rng).sum())
            st["ref_acc_srcfail"]+=int((vis&~ok&refacc).sum()); st["ref_inacc_srcfail"]+=int((vis&~ok&~refacc).sum())
        st=S[rn]; st["N"]+=int(m.sum()); st["vis_hist"]+=np.bincount(vis_cnt,minlength=11)
        st["cov_lt3"]+=int((vis_cnt<3).sum()); st["cov_ge3"]+=int((vis_cnt>=3).sum())
        st["cov_ge3_geofail"]+=int(((vis_cnt>=3)&(gs<3)).sum()); st["cov_ge3_pass"]+=int(((vis_cnt>=3)&(gs>=3)).sum())
        st.setdefault("cov_lt3_geofail",0); st["cov_lt3_geofail"]+=int(((vis_cnt<3)&(gs<3)).sum())
out={}
for rn,st in S.items():
    N=st["N"]; sv_=st["src_vis"]
    out[rn]=dict(N=N,vis_src_count_hist_frac=(st["vis_hist"]/N).round(4).tolist(),
        frac_pixels_visible_in_lt3_src=st["cov_lt3"]/N, frac_pixels_gsum_lt3_AND_vis_lt3=st["cov_lt3_geofail"]/N, frac_pixels_gsum_lt3_AND_vis_ge3=st["cov_ge3_geofail"]/N,
        per_visible_src_pair_consistent=st["src_vis_ok"]/sv_, per_visible_src_fail_px_only=st["src_vis_fail_px_only"]/sv_, per_visible_src_fail_rel_only=st["src_vis_fail_rel_only"]/sv_,
        per_visible_src_fail_both=st["src_vis_fail_both"]/sv_, per_visible_src_fail_range=st["src_vis_fail_range"]/sv_,
        of_failed_visible_pairs_ref_depth_accurate=st["ref_acc_srcfail"]/max(1,st["ref_acc_srcfail"]+st["ref_inacc_srcfail"]))
json.dump(out,open("vis_summary4.json","w"),indent=1)
for rn in out: print("=====",rn); [print(f"  {k}: {v}") for k,v in out[rn].items()]
