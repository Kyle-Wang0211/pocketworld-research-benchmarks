#!/usr/bin/env python3
"""双层尺子(唯一一把,四个臂都用这个,不要各写一把)。
口径:把网格放进 SfM 帧,从 4 个真实拍摄机位投射射线,统计
  双层率 = 第一次与第二次相交间距 >2cm 的射线占比
  间距中位 / 总面积 / 最长边 max
用法: layer2.py <mesh.obj> <名字> [--objframe]
  --objframe: 输入是 aliceVision_meshing 的 OBJ 帧(y,z 相对 SfM 帧取负),会先搬正。
              Poisson/自己写的 ply 若已在 SfM 帧则不要加。
"""
import sys, json, numpy as np, open3d as o3d
PATH=sys.argv[1]; NAME=sys.argv[2]; OBJFRAME='--objframe' in sys.argv
d=json.load(open('/root/av_ep0_off/scene_dense.sfm'))
I=d['intrinsics'][0]; W0=int(I['width']); H0=int(I['height'])
f=float(I['focalLength'])/float(I['sensorWidth'])*W0; pp=[float(x) for x in I['principalPoint']]
poses={p['poseId']:p['pose']['transform'] for p in d['poses']}
views=sorted([v for v in d['views'] if v['poseId'] in poses], key=lambda v:v['path'])
SW,SH=336,250; sca=W0/SW; fx=f/sca; cx=(W0/2+pp[0])/sca; cy=(H0/2+pp[1])/sca
me=o3d.io.read_triangle_mesh(PATH)
V=np.asarray(me.vertices).copy()
if OBJFRAME: V[:,1]*=-1; V[:,2]*=-1
me.vertices=o3d.utility.Vector3dVector(V)
T=np.asarray(me.triangles); a,b,c=V[T[:,0]],V[T[:,1]],V[T[:,2]]
area=0.5*np.linalg.norm(np.cross(b-a,c-a),axis=1).sum()
emax=np.stack([np.linalg.norm(b-a,axis=1),np.linalg.norm(c-b,axis=1),np.linalg.norm(a-c,axis=1)],1).max(1)*1000
scn=o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(me))
hit2=tot=0; gaps=[]
for kk in [0,33,66,99]:
    t=poses[views[kk]['poseId']]
    R=np.array([float(x) for x in t['rotation']]).reshape(3,3); C=np.array([float(x) for x in t['center']])
    u,v=np.meshgrid(np.arange(SW,dtype=np.float32),np.arange(SH,dtype=np.float32))
    dc=np.stack([(u-cx)/fx,(v-cy)/fx,np.ones_like(u)],-1).reshape(-1,3)
    dw=dc@R; dw/=np.linalg.norm(dw,axis=1,keepdims=True)
    res=scn.list_intersections(o3d.core.Tensor(np.concatenate([np.tile(C,(len(dw),1)),dw],1).astype(np.float32)))
    ts=res['t_hit'].numpy(); rid=res['ray_ids'].numpy(); o=np.lexsort((ts,rid)); ts=ts[o]; rid=rid[o]
    i=0
    while i<len(rid):
        j=i
        while j+1<len(rid) and rid[j+1]==rid[i]: j+=1
        tot+=1
        if j>i:
            g=ts[i+1]-ts[i]; gaps.append(g)
            if g>0.02: hit2+=1
        i=j+1
g=np.array(gaps)*1000 if gaps else np.array([0.0])
print(f'{NAME:24s} {len(V):>9,}v {len(T):>10,}f  面积 {area:6.2f}m²  双层(>2cm) {100*hit2/max(tot,1):5.1f}%  间距中位 {np.median(g):6.1f}mm  最长边max {emax.max():5.0f}mm')
