#!/usr/bin/env python3
"""MapAnything per-view depths -> (a) AliceVision depth maps for fuseCut, (b) the raw MapAnything cloud as a
viewer pane, so the eye compares the same depths before and after the visibility graph cut.
Depth stored by AliceVision is distance along the ray; MapAnything's depth_z is planar Z. Views may have been
resized by preprocess_inputs, so K is rescaled to the actual depth-map size.
  ma_to_av_and_bins.py <src_official> <ma_depth_dir> <sfm.sfm> <av_out_dir> <bin_out_dir> <tag>
"""
import sys, json, glob, os, numpy as np, cv2, OpenEXR
SRC, MAD, SFM, AVOUT, BINOUT, TAG = sys.argv[1:7]
os.makedirs(AVOUT, exist_ok=True); os.makedirs(BINOUT, exist_ok=True)
d = json.load(open(SFM)); vid_of = {v["path"].rsplit("/",1)[-1]: v["viewId"] for v in d["views"]}
def read_cam(i):
    L=[l.rstrip() for l in open(f"{SRC}/cams/{i:08d}_cam.txt")]
    return (np.fromstring(" ".join(L[1:5]),sep=" ").reshape(4,4),
            np.fromstring(" ".join(L[7:10]),sep=" ").reshape(3,3))
P=[];C=[]
for f in sorted(glob.glob(f"{MAD}/*_depth.npy")):
    i=int(os.path.basename(f)[:8]); Z0=np.load(f).astype(np.float32)
    # AliceVision relates depth map to view size by an INTEGER downscale, so resample to the view size (768x576)
    Z=cv2.resize(Z0,(768,576),interpolation=cv2.INTER_NEAREST) if Z0.shape!=(576,768) else Z0
    h,w=Z.shape
    E,K=read_cam(i)
    img=cv2.imread(f"{SRC}/images/{i:08d}.jpg")
    u,v=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32))
    ray=np.sqrt(((u-K[0,2])/K[0,0])**2+((v-K[1,2])/K[1,1])**2+1.0)
    ok=Z>0
    dist=np.where(ok, Z*ray, -1.0).astype(np.float32)
    nv=int(ok.sum()); lo=float(dist[ok].min()) if nv else 0.0; hi=float(dist[ok].max()) if nv else 0.0
    vid=vid_of[f"{i:08d}.jpg"]
    OpenEXR.File({"compression":OpenEXR.ZIP_COMPRESSION,"AliceVision:downscale":1,
                  "AliceVision:minDepth":lo,"AliceVision:maxDepth":hi,"AliceVision:nbDepthValues":nv},
                 {"Y":dist}).write(f"{AVOUT}/{vid}_depthMap.exr")
    OpenEXR.File({"compression":OpenEXR.ZIP_COMPRESSION,"AliceVision:downscale":1},
                 {"Y":np.where(ok,-1.0,1.0).astype(np.float32)}).write(f"{AVOUT}/{vid}_simMap.exr")
    x=(u[ok]-K[0,2])/K[0,0]*Z[ok]; y=(v[ok]-K[1,2])/K[1,1]*Z[ok]
    Xw=(np.linalg.inv(E)@np.stack([x,y,Z[ok],np.ones_like(x)],0))[:3].T
    P.append(Xw.astype(np.float32)); C.append(img[ok][:,::-1].astype(np.uint8))
P=np.concatenate(P); C=np.concatenate(C)
print("MapAnything raw cloud:", len(P), "points;", len(glob.glob(f"{AVOUT}/*_depthMap.exr")), "AliceVision maps", flush=True)
with open(f"{AVOUT}/../ma_raw.ply","wb") as fo:
    fo.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"%len(P)).encode())
    r=np.zeros(len(P),dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    r["x"],r["y"],r["z"]=P[:,0],P[:,1],P[:,2]; r["r"],r["g"],r["b"]=C[:,0],C[:,1],C[:,2]; r.tofile(fo)
pos=P.copy(); pos[:,1]*=-1; pos[:,2]*=-1; pos=np.ascontiguousarray(pos.astype("<f4"))
pos.tofile(f"{BINOUT}/{TAG}.pos"); np.ascontiguousarray(C).tofile(f"{BINOUT}/{TAG}.col")
lo_,hi_=np.percentile(pos,1,0),np.percentile(pos,99,0); med=np.median(pos,0)
json.dump({TAG:{"n":int(len(pos)),"center":((lo_+hi_)/2).tolist(),"ext":(hi_-lo_).tolist(),
                "med":med.astype(float).tolist(),"radius":float(np.percentile(np.linalg.norm(pos-med,axis=1),95))}},
          open(f"{BINOUT}/meta_{TAG}.json","w"))
print("wrote", TAG, len(pos), flush=True)
