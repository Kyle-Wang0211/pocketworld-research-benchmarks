import sys, numpy as np
from pathlib import Path
BR="/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python"
sys.path.insert(0, BR); sys.path.insert(0, BR+"/diffmvs")
import pw_diffmvs_sfm_trio as T
from filter import check_geometric_consistency
mn,K_of,w2c_of,cen,obs,pts=T.load_model("lapa")
z=np.load(T.OUT/"p1cache_trio_7full.npz",allow_pickle=True)
fr=z["frames"].tolist(); depth={n:z["depth"][i].astype(np.float32) for i,n in enumerate(fr)}
dr={n:tuple(z["drange"][i]) for i,n in enumerate(fr)}
ok=True
for a,b in [(fr[0],fr[1]),(fr[5],fr[9]),(fr[20],fr[25])]:
    d_ref=depth[a]; K_ref=K_of[a].astype(np.float64); ext_ref=w2c_of[a].astype(np.float64)
    dmin,dmax=dr[a]
    out=check_geometric_consistency(d_ref,K_ref,ext_ref,depth[b],K_of[b].astype(np.float64),
          w2c_of[b].astype(np.float64),dmax,dmin,1.0,0.01,return_ref_depth_src=True)
    reused=out[4]; recomp=T.ref_depth_in_src(d_ref,K_ref,ext_ref,w2c_of[b].astype(np.float64))
    eq=np.array_equal(reused,recomp)
    print(f"{a[:12]}->{b[:12]}: byte-identical={eq} maxdiff={np.abs(reused-recomp).max():.2e}")
    ok = ok and eq
print("RESULT #7:", "BYTE-IDENTICAL PASS" if ok else "FAIL")
