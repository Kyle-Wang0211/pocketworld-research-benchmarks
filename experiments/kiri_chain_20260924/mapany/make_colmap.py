# Our 132 cameras (the exact ones that fused mesh A) as a COLMAP model, written with MapAnything's own colmap utils.
import os, json, numpy as np
from mapanything.utils.colmap import Camera, Image, write_model, rotmat2qvec
S = "/root/mapany_eval/scene"; os.makedirs(f"{S}/images", exist_ok=True); os.makedirs(f"{S}/sparse", exist_ok=True)
order = json.load(open("/root/tsdf_improve/four/cache/order.json"))["order"]
def read_cam(p):
    L = open(p).read().split("\n"); E = np.array([list(map(float, L[i].split())) for i in range(1, 5)])
    K = np.array([list(map(float, L[i].split())) for i in range(7, 10)]); return E, K
cams, imgs = {}, {}
for i, v in enumerate(order, start=1):
    E, K = read_cam(f"/root/mvs_P16k/cams/{v:08d}_cam.txt")
    # COLMAP puts the centre of the top-left pixel at (0.5, 0.5); these cams use integer pixel centres
    cams[i] = Camera(id=i, model="PINHOLE", width=4032, height=3024, params=np.array([K[0, 0], K[1, 1], K[0, 2] + 0.5, K[1, 2] + 0.5]))
    imgs[i] = Image(id=i, qvec=rotmat2qvec(E[:3, :3]), tvec=E[:3, 3], camera_id=i, name=f"{v:08d}.jpg", xys=np.zeros((0, 2)), point3D_ids=np.zeros(0, dtype=int))
    dst = f"{S}/images/{v:08d}.jpg"
    if not os.path.exists(dst): os.symlink(f"/root/mvs_P16k/images/{v:08d}.jpg", dst)
write_model(cams, imgs, {}, f"{S}/sparse", ".bin")
print(len(cams), "cameras,", len(imgs), "images written to", S)
