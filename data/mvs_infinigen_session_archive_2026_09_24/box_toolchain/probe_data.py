import json, glob, os, numpy as np, OpenEXR
d=json.load(open('/root/av_ep0_off/scene_dense.sfm'))
print('intrinsics n=',len(d['intrinsics']),'views n=',len(d['views']),'poses n=',len(d['poses']))
I=d['intrinsics'][0]
print({k:I[k] for k in I if k in ('width','height','focalLength','sensorWidth','principalPoint','intrinsicId','type')})
poses={p['poseId']:p['pose']['transform'] for p in d['poses']}
views={v['viewId']:v for v in d['views']}
maps=sorted(glob.glob('/root/av_ep0_off/filt/*_depthMap.exr'))
print('n depthmaps',len(maps))
def hdr(p):
    with OpenEXR.File(p) as f:
        h=dict(f.header()); Z=np.asarray(f.channels()['Y'].pixels,dtype=np.float32)
    return h,Z
tot=0; valid=0
errs=[]
for k,p in enumerate(maps):
    h,Z=hdr(p)
    vid=os.path.basename(p).split('_')[0]
    C=np.asarray(h['AliceVision:CArr'],dtype=np.float64).reshape(3)
    v=views.get(vid)
    ok = v is not None and v['poseId'] in poses
    if ok:
        Csfm=np.array([float(x) for x in poses[v['poseId']]['center']])
        errs.append(np.linalg.norm(C-Csfm))
    tot+=Z.size; valid+=int((Z>0).sum())
    if k==0:
        print('exr shape',Z.shape,'downscale',h['AliceVision:downscale'],'keys',[x for x in h if x.startswith('AliceVision')])
        print('viewId',vid,'in views',vid in views,'C',C.round(4).tolist())
errs=np.array(errs)
print(f'CArr vs sfm center: n={len(errs)} max={errs.max():.3e} m  median={np.median(errs):.3e} m')
print(f'depth pixels total={tot:,} valid={valid:,} ({100*valid/tot:.1f}%)')
