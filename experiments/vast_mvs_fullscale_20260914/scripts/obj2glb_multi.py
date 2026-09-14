#!/usr/bin/env python3
"""AliceVision texturing 的 OBJ(可能多个 UDIM 图集) -> 单个 GLB(每个图集一个 primitive)。
   obj2glb_multi.py <tex_dir> <out.glb>"""
import numpy as np, struct, json, os, sys, glob
TEX, OUT = sys.argv[1], sys.argv[2]
OBJ = f"{TEX}/texturedMesh.obj"
T = f"{TEX}/_t"
os.system(f"awk '/^v /{{print $2,$3,$4}}' {OBJ} > {T}v.txt")
os.system(f"awk '/^vt /{{print $2,$3}}' {OBJ} > {T}vt.txt")
# 面 + 所属材质序号(usemtl 出现顺序)
os.system("awk '/^usemtl/{if(!(($2) in seen)){seen[$2]=n; ord[n]=$2; n++} m=seen[$2]} "
          "/^f /{gsub(\"/\",\" \"); print m, $2,$3,$4,$5,$6,$7} "
          f"END{{for(i=0;i<n;i++) print \"MTL\", i, ord[i] > \"{T}mtl.txt\"}}' {OBJ} > {T}f.txt")
V  = np.fromstring(open(f"{T}v.txt").read(),  sep=' ').reshape(-1,3)
VT = np.fromstring(open(f"{T}vt.txt").read(), sep=' ').reshape(-1,2)
F  = np.fromstring(open(f"{T}f.txt").read(),  sep=' ', dtype=np.int64).reshape(-1,7)
mtls = [l.split()[2] for l in open(f"{T}mtl.txt")]
print("verts",len(V),"uv",len(VT),"faces",len(F),"materials",mtls, flush=True)
pngs=[]
for name in mtls:                      # material_1001 -> texture_1001.png
    tag=name.split("_")[-1]
    p=f"{TEX}/texture_{tag}.png"
    if not os.path.exists(p): p=sorted(glob.glob(f"{TEX}/texture_*.png"))[len(pngs)]
    pngs.append(p)
def pad(b): return b+b"\x00"*((4-len(b)%4)%4)
bufs=[]; prims=[]; accs=[]; bvs=[]; blob=bytearray()
def add(data):
    off=len(blob); blob.extend(pad(data)); return off, len(data)
for mi,name in enumerate(mtls):
    sub=F[F[:,0]==mi]
    vi=sub[:,[1,3,5]].ravel()-1; ti=sub[:,[2,4,6]].ravel()-1
    key=vi.astype(np.int64)*(len(VT)+1)+ti
    uk,inv=np.unique(key,return_inverse=True)
    uv_i=(uk%(len(VT)+1)).astype(np.int64); uv_v=(uk//(len(VT)+1)).astype(np.int64)
    pos=V[uv_v].astype(np.float32)
    uv=VT[uv_i].astype(np.float32); uv[:,1]=1.0-uv[:,1]
    idx=inv.astype(np.uint32)
    o1,l1=add(pos.tobytes()); o2,l2=add(uv.tobytes()); o3,l3=add(idx.tobytes())
    b0=len(bvs); bvs += [{"buffer":0,"byteOffset":o1,"byteLength":l1,"target":34962},
                         {"buffer":0,"byteOffset":o2,"byteLength":l2,"target":34962},
                         {"buffer":0,"byteOffset":o3,"byteLength":l3,"target":34963}]
    a0=len(accs); accs += [{"bufferView":b0,  "componentType":5126,"count":len(pos),"type":"VEC3",
                            "min":pos.min(0).tolist(),"max":pos.max(0).tolist()},
                           {"bufferView":b0+1,"componentType":5126,"count":len(uv), "type":"VEC2"},
                           {"bufferView":b0+2,"componentType":5125,"count":len(idx),"type":"SCALAR"}]
    prims.append({"attributes":{"POSITION":a0,"TEXCOORD_0":a0+1},"indices":a0+2,"material":mi})
    print(f"  {name}: tris {len(idx)//3:,} verts {len(pos):,}", flush=True)
imgs=[]; texs=[]; mats=[]
for mi,p in enumerate(pngs):
    o,l=add(open(p,"rb").read())
    bv=len(bvs); bvs.append({"buffer":0,"byteOffset":o,"byteLength":l})
    imgs.append({"bufferView":bv,"mimeType":"image/png"}); texs.append({"source":mi,"sampler":0})
    mats.append({"pbrMetallicRoughness":{"baseColorTexture":{"index":mi},
                 "metallicFactor":0.0,"roughnessFactor":1.0}})
g={"asset":{"version":"2.0","generator":"aliceVision_texturing -> glb"},
   "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
   "meshes":[{"primitives":prims}],"materials":mats,"textures":texs,
   "samplers":[{"magFilter":9729,"minFilter":9987,"wrapS":10497,"wrapT":10497}],
   "images":imgs,"accessors":accs,"bufferViews":bvs,"buffers":[{"byteLength":len(blob)}]}
js=pad(json.dumps(g,separators=(',',':')).encode()).replace(b"\x00",b" ")
with open(OUT,"wb") as f:
    f.write(b"glTF"+struct.pack("<II",2,12+8+len(js)+8+len(blob)))
    f.write(struct.pack("<I",len(js))+b"JSON"+js)
    f.write(struct.pack("<I",len(blob))+b"BIN\x00"+bytes(blob))
os.system(f"rm -f {T}*.txt")
print("GLB", os.path.getsize(OUT)/1e6, "MB")
