import numpy as np, struct, json, io, sys, os
from PIL import Image
OBJ="/root/av/tex/texturedMesh.obj"; PNG="/root/av/tex/texture_1001.png"
OUT="/root/av/tex/mesh.glb"
os.system(f"awk '/^v /{{print $2,$3,$4}}' {OBJ} > /root/av/tex/_v.txt")
os.system(f"awk '/^vt /{{print $2,$3}}' {OBJ} > /root/av/tex/_vt.txt")
os.system(f"awk '/^f /{{print $2,$3,$4}}' {OBJ} | tr '/' ' ' > /root/av/tex/_f.txt")
V  = np.fromstring(open("/root/av/tex/_v.txt").read(), sep=' ', dtype=np.float64).reshape(-1,3)
VT = np.fromstring(open("/root/av/tex/_vt.txt").read(), sep=' ', dtype=np.float64).reshape(-1,2)
F  = np.fromstring(open("/root/av/tex/_f.txt").read(), sep=' ', dtype=np.int64).reshape(-1,6)
print("parsed", V.shape, VT.shape, F.shape, flush=True)
vi = F[:,[0,2,4]].ravel()-1; ti = F[:,[1,3,5]].ravel()-1
key = vi.astype(np.int64)*(len(VT)+1) + ti
uk, inv = np.unique(key, return_inverse=True)
uv_i = (uk % (len(VT)+1)).astype(np.int64); uv_v = (uk // (len(VT)+1)).astype(np.int64)
pos = V[uv_v].astype(np.float32)
uv  = VT[uv_i].astype(np.float32); uv[:,1] = 1.0 - uv[:,1]   # OBJ 左下原点 -> glTF 左上
idx = inv.astype(np.uint32)
print("verts", len(pos), "tris", len(idx)//3, flush=True)
im = Image.open(PNG).convert("RGB")
jpg = open(PNG,"rb").read()
print("texture png", len(jpg)/1e6, "MB", flush=True)
def pad(b): return b + b"\x00"*((4-len(b)%4)%4)
bufs=[pos.tobytes(), uv.tobytes(), idx.tobytes(), jpg]
offs=[]; blob=b""
for b in bufs:
    offs.append(len(blob)); blob += pad(b)
g = {
 "asset":{"version":"2.0","generator":"aliceVision_texturing -> glb"},
 "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
 "meshes":[{"primitives":[{"attributes":{"POSITION":0,"TEXCOORD_0":1},"indices":2,"material":0}]}],
 "materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0},"metallicFactor":0.0,"roughnessFactor":1.0}}],
 "textures":[{"source":0,"sampler":0}],"samplers":[{"magFilter":9729,"minFilter":9987,"wrapS":10497,"wrapT":10497}],
 "images":[{"bufferView":3,"mimeType":"image/png"}],
 "accessors":[
  {"bufferView":0,"componentType":5126,"count":len(pos),"type":"VEC3",
   "min":pos.min(0).tolist(),"max":pos.max(0).tolist()},
  {"bufferView":1,"componentType":5126,"count":len(uv),"type":"VEC2"},
  {"bufferView":2,"componentType":5125,"count":len(idx),"type":"SCALAR"}],
 "bufferViews":[
  {"buffer":0,"byteOffset":offs[0],"byteLength":len(bufs[0]),"target":34962},
  {"buffer":0,"byteOffset":offs[1],"byteLength":len(bufs[1]),"target":34962},
  {"buffer":0,"byteOffset":offs[2],"byteLength":len(bufs[2]),"target":34963},
  {"buffer":0,"byteOffset":offs[3],"byteLength":len(bufs[3])}],
 "buffers":[{"byteLength":len(blob)}]}
js = pad(json.dumps(g,separators=(',',':')).encode()).replace(b"\x00",b" ")
with open(OUT,"wb") as f:
    f.write(b"glTF"+struct.pack("<II",2,12+8+len(js)+8+len(blob)))
    f.write(struct.pack("<I",len(js))+b"JSON"+js)
    f.write(struct.pack("<I",len(blob))+b"BIN\x00"+blob)
print("GLB", os.path.getsize(OUT)/1e6, "MB")
