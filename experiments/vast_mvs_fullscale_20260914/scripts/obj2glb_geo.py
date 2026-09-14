#!/usr/bin/env python3
"""纯几何 OBJ -> GLB(只有位置+索引,着色靠屏幕导数取面法线)。 obj2glb_geo.py <in.obj> <out.glb>"""
import numpy as np, struct, json, os, sys
OBJ, OUT = sys.argv[1], sys.argv[2]
T = OUT + "._"
os.system(f"awk '/^v /{{print $2,$3,$4}}' {OBJ} > {T}v.txt")
# 面既可能是 "f a b c" 也可能是 "f a/t b/t c/t"(带纹理),按 gsub 后的字段数分辨
os.system(f"awk '/^f /{{gsub(\"/\",\" \"); if (NF==4) print $2,$3,$4; else print $2,$4,$6}}' {OBJ} > {T}f.txt")
V=np.fromstring(open(f"{T}v.txt").read(),sep=' ').reshape(-1,3).astype(np.float32)
F=np.fromstring(open(f"{T}f.txt").read(),sep=' ',dtype=np.int64).reshape(-1,3)
idx=(F-1).astype(np.uint32).ravel()
print("verts",len(V),"tris",len(F),flush=True)
def pad(b): return b+b"\x00"*((4-len(b)%4)%4)
blob=bytearray(); offs=[]
for b in (V.tobytes(), idx.tobytes()):
    offs.append(len(blob)); blob.extend(pad(b))
g={"asset":{"version":"2.0","generator":"aliceVision_meshing -> glb (geometry only)"},
   "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
   "meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1,"material":0}]}],
   "materials":[{"pbrMetallicRoughness":{"baseColorFactor":[0.72,0.72,0.72,1],
                 "metallicFactor":0.0,"roughnessFactor":1.0}}],
   "accessors":[{"bufferView":0,"componentType":5126,"count":len(V),"type":"VEC3",
                 "min":V.min(0).tolist(),"max":V.max(0).tolist()},
                {"bufferView":1,"componentType":5125,"count":len(idx),"type":"SCALAR"}],
   "bufferViews":[{"buffer":0,"byteOffset":offs[0],"byteLength":len(V.tobytes()),"target":34962},
                  {"buffer":0,"byteOffset":offs[1],"byteLength":len(idx.tobytes()),"target":34963}],
   "buffers":[{"byteLength":len(blob)}]}
js=pad(json.dumps(g,separators=(',',':')).encode()).replace(b"\x00",b" ")
with open(OUT,"wb") as f:
    f.write(b"glTF"+struct.pack("<II",2,12+8+len(js)+8+len(blob)))
    f.write(struct.pack("<I",len(js))+b"JSON"+js)
    f.write(struct.pack("<I",len(blob))+b"BIN\x00"+bytes(blob))
os.system(f"rm -f {T}*.txt")
print("GLB", os.path.getsize(OUT)/1e6, "MB")
