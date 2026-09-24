# Page assets for the rebuilt textured mesh: GLB (same trimesh conversion as on the old box: force="scene",
# process=False), 12 capture views as OpenGL view matrices, and a stats file.
import json, os, numpy as np, trimesh
T = "/root/tsdf_improve/tex_K1"
P = "/root/page_cmp"
os.makedirs(f"{P}/tex", exist_ok=True)
sc = trimesh.load(f"{T}/K1_textured.obj", force="scene", process=False)
sc.export(f"{T}/K1_textured.glb")
nf = sum(len(g.faces) for g in sc.geometry.values())
print("GLB", os.path.getsize(f"{T}/K1_textured.glb"), "bytes", len(sc.geometry), "geoms", nf, "faces")

# capture views: every 11th photo, OpenGL view = diag(1,-1,-1) @ [R|t]; fovy from fy of the 4032x3024 photos
cams = []
names = sorted(f[:-8] for f in os.listdir("/root/mvs_P16k/cams") if f.endswith("_cam.txt"))
for i in range(0, len(names), 11):
    L = open(f"/root/mvs_P16k/cams/{names[i]}_cam.txt").read().split()
    E = np.array(L[1:17], float).reshape(4, 4); K = np.array(L[18:27], float).reshape(3, 3)
    V = np.diag([1.0, -1.0, -1.0, 1.0]) @ E
    R, t = E[:3, :3], E[:3, 3]
    cams.append(dict(view=int(names[i]), center=(-R.T @ t).tolist(), fwd=(R.T @ np.array([0, 0, 1.0])).tolist(),
                     fovy=float(2 * np.arctan(1512 / K[1, 1])), viewmat=V.T.ravel().tolist()))
json.dump(cams, open(f"{P}/cams.json", "w"))
print(len(cams), "capture views; view 0 fovy", round(cams[0]["fovy"], 4))
